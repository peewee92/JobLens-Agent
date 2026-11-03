"""Session-owned BYOK connection and explicit, idempotent single-call commands."""
from hashlib import sha256
import json
from fastapi import APIRouter
from pydantic import BaseModel, ConfigDict, Field, StrictBool
import httpx
from app.byok.context import ConnectionInput, current_model
from app.byok.calls import OnceTransport, execution
from app.byok.transport import validate_url
from app.demo.sessions import DemoError

router = APIRouter()

class ProfilePlanInput(BaseModel):
    model_config = ConfigDict(extra='forbid')
    resumeText: str = Field(min_length=50, max_length=12000)

class CallInput(BaseModel):
    model_config = ConfigDict(extra='forbid')
    actionId: str = Field(min_length=1, max_length=100, pattern=r'^[A-Za-z0-9_-]+$')
    planDigest: str = Field(min_length=64, max_length=64)
    acknowledgedPriorRequestId: str | None = Field(default=None, max_length=100)
    confirmed: StrictBool = False
    maxProviderCalls: int = Field(default=0, strict=True, ge=0, le=1)


def state():
    s = current_model.get()
    if s is None or s.mode != 'byok':
        raise DemoError('byok_required', 403, '请先进入自带模型模式。')
    return s


def metadata(s):
    c = s.connection
    return {'connected': c is not None, 'version': s.version, 'mode': s.mode, 'seed': s.seed,
        'connection': c.model_dump(exclude={'apiKey'}) if c else None, 'busy': s.busy,
        'recentCalls': [{k:v for k,v in r.items() if k != 'result'} for _,r in list(s.calls.values())[-10:]]}


@router.get('/model-connection')
def get_connection():
    return metadata(state())


@router.put('/model-connection')
def put_connection(value: ConnectionInput):
    s = state()
    try:
        value.baseUrl = validate_url(value.baseUrl)
    except ValueError:
        raise DemoError('model_address_invalid', 422, '请填写可解析到公网的 HTTPS 模型地址，不支持内网、跳转或 URL 内嵌凭证。')
    with s.lock:
        if s.busy:
            raise DemoError('model_busy', 409, '操作进行中，暂不能更换模型连接。')
        s.connection = value
        s.version += 1
        s.plans.clear()
    return metadata(s)


@router.delete('/model-connection')
def delete_connection():
    s = state()
    with s.lock:
        if s.busy:
            raise DemoError('model_busy', 409, '操作进行中，暂不能断开连接。')
        s.connection = None
        s.version += 1
        s.plans.clear()
    return metadata(s)


def plan(kind, text=''):
    s = state()
    if not s.connection:
        raise DemoError('model_not_connected', 409, '请先连接自己的模型。')
    model = s.connection.profileModel or s.connection.model if kind == 'profile' else s.connection.model
    payload = dict(kind=kind, version=s.version, model=model, inputHash=sha256(text.encode()).hexdigest(),
                   maxProviderCalls=1, maxOutputTokens=4096 if kind == 'profile' else 256, timeoutSeconds=60)
    digest = sha256(json.dumps(payload, sort_keys=True).encode()).hexdigest()
    with s.lock:
        if len(s.plans) >= 20:
            s.plans.pop(next(iter(s.plans)))
        s.plans[digest] = (payload, text)
    return dict(payload, planDigest=digest, cost='unknown', inputCharacters=len(text))


@router.get('/model-connection/test-plan')
def test_plan():
    return plan('test')


@router.post('/profile-call-plan')
def profile_plan(value: ProfilePlanInput):
    return plan('profile', value.resumeText)


class RecordedTransport(OnceTransport):
    def __init__(self, s, record):
        super().__init__(s)
        self.record = record
    def handle_request(self, request):
        self.record['attempts'] += 1
        response = super().handle_request(request)
        self.record['responseStatus'] = response.status_code
        try:
            usage = response.json().get('usage', {})
            for key, names in [('inputTokens', ('input_tokens','prompt_tokens')), ('outputTokens', ('output_tokens','completion_tokens'))]:
                self.record[key] = next((usage[n] for n in names if type(usage.get(n)) is int and usage[n] >= 0), None)
        except (ValueError, AttributeError, TypeError):
            pass
        return response


def execute(kind, command):
    s = state()
    # Serialize claim/config changes and hold the execution lease throughout the send.
    with execution(s):
        old = s.calls.get(command.actionId)
        identity = (kind, command.planDigest, command.confirmed, command.maxProviderCalls, command.acknowledgedPriorRequestId)
        if old:
            if old[0] != identity:
                raise DemoError('call_conflict', 409, '请求标识已用于其他操作。')
            return old[1]
        prior = next((r for ident, r in reversed(list(s.calls.values())) if ident[0] == kind and r['status'] in ('running', 'uncertain')), None)
        if prior and command.acknowledgedPriorRequestId != prior['actionId']:
            raise DemoError('prior_request_uncertain', 409, '上次请求结果未知，请先查询并明确确认已有费用风险，不会自动重新调用。')
        if not command.confirmed or command.maxProviderCalls != 1:
            raise DemoError('model_authorization_required', 409, '请确认本次调用范围及费用。')
        stored = s.plans.get(command.planDigest)
        if not stored or stored[0]['version'] != s.version or stored[0]['kind'] != kind:
            raise DemoError('model_plan_stale', 409, '配置或输入已变化，请重新查看调用计划。')
        if len(s.calls) >= 20:
            raise DemoError('call_limit', 429, '会话调用记录已达上限，请导出资料后重新开始。')
        p, text = stored
        record = dict(kind=kind, actionId=command.actionId, status='running', model=p['model'], connectionVersion=s.version,
                      attempts=0, inputTokens=None, outputTokens=None, responseStatus=None,
                      errorCode=None, cost='unknown', result=None)
        s.calls[command.actionId] = (identity, record)
        c = s.connection
        try:
            with httpx.Client(transport=RecordedTransport(s, record), timeout=60, follow_redirects=False, trust_env=False) as client:
                if kind == 'profile':
                    from app.llm.profile_extractors import OpenAIProfileExtractor
                    from app.workflows.profile_extraction import ProposeProfileFromResumeWorkflow
                    from app.api.deps import get_trace_uow_factory
                    from app.api.v1.schemas.profile_extraction import ProfileExtractionProposalResponse
                    extractor = OpenAIProfileExtractor(api_key=c.apiKey.get_secret_value(), model=p['model'],
                        base_url=c.baseUrl, api_style=c.apiStyle, max_completion_tokens=4096, enable_thinking=c.enableThinking, client=client)
                    result = ProposeProfileFromResumeWorkflow(extractor, get_trace_uow_factory()).execute(text)
                    record['result'] = ProfileExtractionProposalResponse.from_proposal(result).model_dump(mode='json', by_alias=True)
                else:
                    schema = {'type':'object', 'properties':{'ok':{'type':'boolean'}}, 'required':['ok'], 'additionalProperties':False}
                    if c.apiStyle == 'chat_completions':
                        path = '/chat/completions'
                        body = dict(model=c.model, messages=[{'role':'user','content':'Return {"ok":true} as JSON.'}],
                            max_completion_tokens=256, response_format={'type':'json_schema','json_schema':{'name':'connection_test','strict':True,'schema':schema}})
                    else:
                        path = '/responses'
                        body = dict(model=c.model, input='Return {"ok":true} as JSON.', max_output_tokens=256,
                            text={'format':{'type':'json_schema','name':'connection_test','strict':True,'schema':schema}})
                    if c.apiStyle == 'chat_completions' and c.enableThinking is not None:
                        body['enable_thinking'] = c.enableThinking
                    r = client.post(c.baseUrl + path, headers={'Authorization': 'Bearer ' + c.apiKey.get_secret_value()}, json=body)
                    r.raise_for_status()
                    from app.llm.profile_extractors import _response_output_text, _chat_completion_output_text
                    read_text = _response_output_text if c.apiStyle == "responses" else _chat_completion_output_text
                    if json.loads(read_text(r.json())) != {'ok': True}:
                        raise ValueError('invalid_structured_output')
                    record['result'] = {'ok':True}
                record['status'] = 'completed'
        except Exception:
            code = record['responseStatus']
            record['status'] = 'uncertain' if record['attempts'] and code is None else 'failed'
            record['errorCode'] = {401:'provider_auth_failed',403:'provider_forbidden',402:'provider_payment_required',
                404:'provider_model_or_endpoint_missing',429:'provider_rate_limited'}.get(code, 'provider_request_uncertain' if code is None and record['attempts'] else 'provider_output_invalid')
        return record


@router.post('/model-connection/test')
def test_connection(command: CallInput):
    return execute('test', command)


@router.post('/profile-calls')
def profile_call(command: CallInput):
    return execute('profile', command)


@router.get('/profile-calls/{action_id}')
def call_status(action_id: str):
    item = state().calls.get(action_id)
    if not item:
        raise DemoError('model_call_not_found', 404, '当前会话未找到该调用。')
    return item[1]

@router.get('/session-export')
def export_session():
    from app.db.context import current_database
    from sqlalchemy import inspect, text
    from fastapi.responses import JSONResponse
    from fastapi.encoders import jsonable_encoder
    s = state()
    database = current_database.get()
    # Positive table allowlist: deliberately excludes traces, secrets and internal checkpoints.
    allowed = ('user_profiles', 'profile_evidence', 'profile_skills', 'profile_skill_evidence',
               'search_intents', 'jobs', 'job_requirement_extractions', 'job_requirements',
               'match_reports', 'application_workspaces', 'execution_action_items', 'resume_variants', 'application_timeline_events',
               'requirement_calls', 'semantic_calls')
    tables = {}
    with database.engine.connect() as conn:
        present = set(inspect(conn).get_table_names())
        for name in allowed:
            if name in present:
                tables[name] = [dict(row) for row in conn.execute(text(f'SELECT * FROM {name} LIMIT 1000')).mappings()]
    return JSONResponse(jsonable_encoder({'format':'joblens-session-export-v1', 'seed':s.seed,
        'tables':tables, 'modelCalls':[v[1] for v in s.calls.values()]}),
        headers={'Content-Disposition':'attachment; filename="joblens-session.json"', 'Cache-Control':'no-store'})
