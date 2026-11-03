"""Public session tests with mocked model transport; no paid calls."""
import json
import socket
from concurrent.futures import ThreadPoolExecutor
from threading import Event
import httpx
import pytest
from fastapi.testclient import TestClient
from app.demo.public_app import create_public_app
from app.demo.sessions import DemoSessions
from app.byok.transport import validate_url, PublicNetworkBackend
from .test_public_demo import template, SECRET, ORIGIN, headers

@pytest.fixture
def setup_byok(tmp_path, template, monkeypatch):
    now=[100.];manager=DemoSessions(tmp_path/'sessions',template,clock=lambda:now[0])
    monkeypatch.setattr(socket,'getaddrinfo',lambda *a,**k:[(socket.AF_INET,socket.SOCK_STREAM,6,'',('93.184.216.34',443))])
    sent=[]
    def handle(req):
        sent.append(req)
        return httpx.Response(200,json={'choices':[{'message':{'content':'{"ok":true}'}}],'usage':{'prompt_tokens':10,'completion_tokens':4}})
    handlers={'send':handle}
    import app.byok.calls as module
    monkeypatch.setattr(module,'PublicTransport',lambda:httpx.MockTransport(lambda req:handlers['send'](req)))
    with TestClient(create_public_app(manager,secret=SECRET,origin=ORIGIN,byok_enabled=True)) as c:
        yield c,manager,now,sent,handlers
    manager.close()

def start(c,who='a'):
    r=c.post('/api/v1/demo/session',headers={**headers(),'X-Demo-Client':who},json={'mode':'byok','seed':'sample'})
    assert r.status_code==200,r.text
    return r.json()['sessionToken']

def connect(c,t,key='secret-a',model='model-a'):
    r=c.put('/api/v1/model-connection',headers=headers(t),json={'baseUrl':'https://provider.example/v1','apiKey':key,'model':model})
    assert r.status_code==200,r.text
    assert key not in r.text
    return r.json()

def command(c,t):
    r=c.get('/api/v1/model-connection/test-plan',headers=headers(t));assert r.status_code==200,r.text
    return dict(actionId='test-one',planDigest=r.json()['planDigest'],confirmed=True,maxProviderCalls=1)

def test_connection_no_calls_replay_and_isolation(setup_byok):
    c,m,_,sent,_=setup_byok;a,b=start(c),start(c,'b')
    connect(c,a);connect(c,b,'secret-b','model-b');assert not sent
    p=command(c,a);r=c.post('/api/v1/model-connection/test',headers=headers(a),json=p)
    assert r.status_code==200,r.text
    assert r.json()['status']=='completed' and r.json()['attempts']==1
    assert r.json()['inputTokens']==10 and r.json()['outputTokens']==4
    assert len(sent)==1 and sent[0].headers['Authorization']=='Bearer secret-a'
    assert c.post('/api/v1/model-connection/test',headers=headers(a),json=p).json()==r.json()
    assert len(sent)==1
    assert c.get('/api/v1/profile-calls/test-one',headers=headers(b)).status_code==404
    assert c.get('/api/v1/model-connection',headers=headers(b)).json()['connection']['model']=='model-b'
    e=c.get('/api/v1/session-export',headers=headers(a));assert e.status_code==200
    assert 'secret-a' not in e.text and 'secret-b' not in e.text
    for token in (a,b):
        with m.acquire(token) as ctx:assert b'secret-' not in (ctx.directory/'demo.db').read_bytes()

def test_stale_config_consent_and_validation_no_echo(setup_byok):
    c,_,_,sent,_=setup_byok;a=start(c);connect(c,a);p=command(c,a)
    connect(c,a,'secret-new')
    assert c.post('/api/v1/model-connection/test',headers=headers(a),json=p).status_code==409
    p=command(c,a)
    for v in (False,'true'):
        assert c.post('/api/v1/model-connection/test',headers=headers(a),json={**p,'confirmed':v}).status_code in (409,422)
    r=c.put('/api/v1/model-connection',headers=headers(a),json={'apiKey':'never-echo','baseUrl':{},'model':'x'})
    assert r.status_code==422 and 'never-echo' not in r.text and not sent

@pytest.mark.parametrize('status',[401,402,403,404,429,500])
def test_provider_failures_never_retry_or_leak(setup_byok,status):
    c,_,_,sent,h=setup_byok;a=start(c);connect(c,a)
    def fail(req):
        sent.append(req);return httpx.Response(status,json={'error':'secret-a private provider error'})
    h['send']=fail;p=command(c,a)
    r=c.post('/api/v1/model-connection/test',headers=headers(a),json=p)
    assert r.status_code==200 and r.json()['status']=='failed'
    assert 'secret-a' not in r.text
    assert c.post('/api/v1/model-connection/test',headers=headers(a),json=p).json()==r.json() and len(sent)==1

def test_uncertain_no_replay(setup_byok):
    c,_,_,sent,h=setup_byok;a=start(c);connect(c,a)
    def fail(req):sent.append(req);raise httpx.ReadTimeout('secret-a')
    h['send']=fail;p=command(c,a)
    r=c.post('/api/v1/model-connection/test',headers=headers(a),json=p)
    assert r.json()['status']=='uncertain' and 'secret-a' not in r.text
    assert c.post('/api/v1/model-connection/test',headers=headers(a),json=p).json()==r.json() and len(sent)==1

def test_busy_blocks_config_change(setup_byok):
    c,_,_,sent,h=setup_byok;a=start(c);connect(c,a);entered,release=Event(),Event()
    def wait(req):
        sent.append(req);entered.set();assert release.wait(5)
        return httpx.Response(200,json={'choices':[{'message':{'content':'{"ok":true}'}}]})
    h['send']=wait;p=command(c,a)
    with ThreadPoolExecutor(max_workers=1) as pool:
        f=pool.submit(c.post,'/api/v1/model-connection/test',headers=headers(a),json=p)
        assert entered.wait(3)
        assert c.delete('/api/v1/model-connection',headers=headers(a)).status_code==409
        assert c.post('/api/v1/model-connection/test',headers=headers(a),json=p).status_code==409
        release.set();assert f.result().json()['status']=='completed'

def test_expiry_erases_key(setup_byok):
    c,m,now,_,_=setup_byok;a=start(c);connect(c,a);s=m.state(a)
    now[0]+=1801;m.collect()
    assert s.connection is None and not s.calls and not s.plans
    assert c.get('/api/v1/model-connection',headers=headers(a)).status_code==410

def test_default_off_and_sample_denied(setup_byok):
    c,m,_,sent,_=setup_byok
    t=c.post('/api/v1/demo/session',headers=headers()).json()['sessionToken']
    assert c.get('/api/v1/model-connection',headers=headers(t)).status_code==403
    with TestClient(create_public_app(m,secret=SECRET,origin=ORIGIN)) as off:
        assert off.post('/api/v1/demo/session',headers=headers(),json={'mode':'byok'}).status_code==403
    assert not sent

@pytest.mark.parametrize('url',['http://example.com/v1','https://user:pass@example.com/v1','https://example.com/v1?key=x','https://example.com/v1#x','https://example.com:8443/v1'])
def test_reject_url_shape(url):
    with pytest.raises(ValueError):validate_url(url)

@pytest.mark.parametrize('ip',['127.0.0.1','10.0.0.1','169.254.169.254','::1','fd00::1','::ffff:8.8.8.8'])
def test_reject_private_dns(monkeypatch,ip):
    monkeypatch.setattr(socket,'getaddrinfo',lambda *a,**k:[(0,0,0,'',(ip,443))])
    with pytest.raises(ValueError):validate_url('https://evil.example/v1')

def test_connect_pins_numeric_ip(monkeypatch):
    from httpcore._backends.sync import SyncBackend
    monkeypatch.setattr(socket,'getaddrinfo',lambda *a,**k:[(0,0,0,'',('93.184.216.34',443))])
    sent=[];monkeypatch.setattr(SyncBackend,'connect_tcp',lambda self,host,port,timeout,**kw:sent.append((host,port)))
    PublicNetworkBackend().connect_tcp('provider.example',443,60);assert sent==[('93.184.216.34',443)]
    monkeypatch.setattr(socket,'getaddrinfo',lambda *a,**k:[(0,0,0,'',('127.0.0.1',443))])
    with pytest.raises(ValueError):PublicNetworkBackend().connect_tcp('provider.example',443,60)

def test_profile_real_adapter_proposal_not_confirmed_facts(setup_byok):
    c,m,_,sent,h=setup_byok;a=start(c);connect(c,a)
    resume='我负责使用 Python 开发并维护 FastAPI 服务，实现岗位数据清洗和接口测试，参与服务设计和故障排查，所有经历均为合成验收材料。'
    result={'headline':'合成工程师','yearsOfExperience':None,'evidence':[{'key':'p','type':'project','summary':'使用 Python 开发并维护 FastAPI 服务','source':'resume','evidenceSpan':'使用 Python 开发并维护 FastAPI 服务'}], 'skills':[{'name':'Python','level':'working','evidenceKeys':['p']}],'warnings':[]}
    def handle(req):
        sent.append(req);assert req.headers['Authorization']=='Bearer secret-a'
        return httpx.Response(200,json={'choices':[{'message':{'content':json.dumps(result,ensure_ascii=False)}}]})
    h['send']=handle
    before=c.get('/api/v1/profile',headers=headers(a)).json()
    p=c.post('/api/v1/profile-call-plan',headers=headers(a),json={'resumeText':resume})
    assert p.status_code==200,p.text
    assert not sent
    payload=dict(actionId='profile-one',planDigest=p.json()['planDigest'],confirmed=True,maxProviderCalls=1)
    r=c.post('/api/v1/profile-calls',headers=headers(a),json=payload)
    assert r.status_code==200 and r.json()['status']=='completed',r.text
    assert r.json()['result']['evidence'][0]['evidenceSpan'] in resume
    assert c.get('/api/v1/profile',headers=headers(a)).json()==before
    assert c.post('/api/v1/profile-calls',headers=headers(a),json=payload).json()==r.json() and len(sent)==1


def test_synthetic_inputs_require_fresh_real_extraction_then_confirm_match_and_action(setup_byok):
    from .test_authorized_requirement_call import DESCRIPTION
    c,m,_,sent,h=setup_byok;a=start(c);connect(c,a)
    with m.acquire(a) as ctx,ctx.sessions() as db:
        from sqlalchemy import text
        assert db.execute(text('SELECT count(*) FROM match_reports')).scalar_one()==0
        assert db.execute(text('SELECT count(*) FROM job_requirement_extractions')).scalar_one()==0
    imported=c.post('/api/v1/job-imports/manual',headers=headers(a),json={'title':'后端工程师','company':'合成公司','description':DESCRIPTION})
    assert imported.status_code==201,imported.text
    job=imported.json()['jobId'];path='/api/v1/jobs/'+job
    def handle(req):
        sent.append(req)
        output={'requirements':[{'type':'skill','originalText':'熟练掌握 Python 和 FastAPI','normalizedCapability':'Python','importance':'must_have','sourceCandidateId':'S0002','confidence':.95}]}
        return httpx.Response(200,json={'choices':[{'message':{'content':json.dumps(output)}}],'usage':{'prompt_tokens':22,'completion_tokens':11}})
    h['send']=handle
    plan=c.get(path+'/requirement-call-plan',headers=headers(a));assert plan.status_code==200,plan.text
    payload=dict(actionId='extract',planDigest=plan.json()['planDigest'],confirmed=True,maxProviderCalls=1)
    r=c.post(path+'/requirement-calls',headers=headers(a),json=payload)
    assert r.status_code==200 and r.json()['status']=='completed',r.text
    assert len(sent)==1
    assert c.post(path+'/requirement-calls',headers=headers(a),json=payload).json()==r.json() and len(sent)==1
    extracted=c.get(path+'/requirements',headers=headers(a)).json()
    assert c.post(path+'/requirement-confirmations',headers=headers(a),json=dict(actionId='confirm',extractionId=extracted['extractionId'],inputHash=extracted['inputHash'],factsDigest=extracted['factsDigest'],confirmed=True)).status_code==200
    semantic=c.get(path+'/semantic-call-plan',headers=headers(a))
    assert semantic.status_code==200,semantic.text
    assert semantic.json()['blockerCode']=='semantic_model_not_needed',semantic.text
    report=c.post(path+'/match-report',headers=headers(a))
    assert report.status_code==200,report.text
    assert report.json()['providerCalls']==0 and len(sent)==1
    payload=dict(threadId='real-flow',runId='real-run',requestId='real-request',jobIds=[job],topN=1)
    started=c.post('/api/v1/career-agent/runs',headers=headers(a),json=payload)
    assert started.status_code==200,started.text
    data=started.json();assert data['status']=='interrupted'
    completed=c.post('/api/v1/career-agent/runs/real-flow/resume',headers=headers(a),json=dict(interruptId=data['interruptId'],actionId='approve',decision='approve'))
    assert completed.status_code==200 and completed.json()['status']=='completed',completed.text
    result=c.get('/api/v1/career-agent/runs/real-flow/result',headers=headers(a)).json()
    receipt=c.post('/api/v1/career-agent/runs/real-flow/execution',headers=headers(a),json=dict(commandId='execute',resultId=result['resultId'],jobIds=result['selectedJobIds']))
    assert receipt.status_code==200,receipt.text
    assert receipt.json()['items'] and len(sent)==1

def test_semantic_uses_session_key_and_rejects_legacy_shortcut(setup_byok):
    from .test_authorized_requirement_call import DESCRIPTION
    c,_,_,sent,h=setup_byok;a=start(c);connect(c,a,'semantic-secret','semantic-model')
    before=c.get('/api/v1/profile',headers=headers(a)).json()
    r=c.put('/api/v1/profile',headers=headers(a),json={'expectedVersion':before['version'],'headline':'合成后端工程师','yearsOfExperience':2,
        'evidence':[{'key':'p','type':'project','summary':'使用 Python 开发并维护服务','source':'合成验收'}],'skills':[]})
    assert r.status_code==200,r.text
    job=c.post('/api/v1/job-imports/manual',headers=headers(a),json={'title':'合成岗位','company':'合成公司','description':DESCRIPTION}).json()['jobId']
    path='/api/v1/jobs/'+job
    def handle(req):
        sent.append(req);assert req.headers['Authorization']=='Bearer semantic-secret'
        body=json.loads(req.content)
        assert body['model']=='semantic-model'
        if 'semantic_match' in json.dumps(body['response_format']):
            data=json.loads(body['messages'][1]['content'])
            output={'assessments':[{'requirementId':r['requirementId'],'verdict':'partial','evidenceIds':[r['candidates'][0]['evidenceId']],'reason':'存在相关经历，仍需核实完整能力。'} for r in data['requirements']]}
        else:
            output={'requirements':[{'type':'skill','originalText':'熟练掌握 Python 和 FastAPI','normalizedCapability':'Python','importance':'must_have','sourceCandidateId':'S0002','confidence':.95}]}
        return httpx.Response(200,json={'choices':[{'message':{'content':json.dumps(output)}}]})
    h['send']=handle
    p=c.get(path+'/requirement-call-plan',headers=headers(a)).json()
    r=c.post(path+'/requirement-calls',headers=headers(a),json=dict(actionId='extract',planDigest=p['planDigest'],confirmed=True,maxProviderCalls=1))
    assert r.json()['status']=='completed',r.text
    e=c.get(path+'/requirements',headers=headers(a)).json()
    r=c.post(path+'/requirement-confirmations',headers=headers(a),json=dict(actionId='confirm',extractionId=e['extractionId'],inputHash=e['inputHash'],factsDigest=e['factsDigest'],confirmed=True))
    assert r.status_code==200,r.text
    assert c.post(path+'/match-report',headers=headers(a)).status_code!=200 # cannot turn needed semantics into a fake offline result
    p=c.get(path+'/semantic-call-plan',headers=headers(a));assert p.status_code==200,p.text
    assert p.json()['available'],p.text
    payload=dict(actionId='semantic',planDigest=p.json()['planDigest'],confirmed=True,maxProviderCalls=1)
    r=c.post(path+'/semantic-calls',headers=headers(a),json=payload)
    assert r.json()['status']=='completed',r.text
    assert len(sent)==2
    assert c.post(path+'/semantic-calls',headers=headers(a),json=payload).json()==r.json() and len(sent)==2

def test_five_visitors_allow_only_two_model_executions():
    from app.byok.context import ModelSession, ConnectionInput
    from app.byok.calls import execution
    from app.demo.sessions import DemoError
    from threading import Barrier, Lock
    barrier=Barrier(5);release=Event();lock=Lock();counts={'active':0,'maximum':0,'busy':0}
    def run(_):
        state=ModelSession(mode='byok',connection=ConnectionInput(baseUrl='https://example.com/v1',apiKey='fake',model='fake'))
        barrier.wait(timeout=5)
        try:
            with execution(state):
                with lock:
                    counts['active']+=1;counts['maximum']=max(counts['maximum'],counts['active'])
                release.wait(2)
                with lock:counts['active']-=1
                return 'executed'
        except DemoError as exc:
            with lock:
                counts['busy']+=1
                if counts['busy']==3:release.set()
            return exc.code
    with ThreadPoolExecutor(max_workers=5) as pool:results=list(pool.map(run,range(5)))
    assert results.count('executed')==2 and results.count('model_capacity')==3 and counts['maximum']==2


def test_block_redirect_and_echoed_key(setup_byok):
    c,_,_,sent,h=setup_byok;a=start(c);connect(c,a)
    def redirect(req):
        sent.append(req);return httpx.Response(302,headers={'location':'http://169.254.169.254/latest/meta-data'})
    h['send']=redirect
    r=c.post('/api/v1/model-connection/test',headers=headers(a),json=command(c,a))
    assert r.json()['status']=='failed' and len(sent)==1
    # Same short-lived memory store is bounded and schema matches shared contract.
    from app.byok.context import ConnectionInput
    from pathlib import Path
    contract=json.loads((Path(__file__).parents[3]/'packages/contracts/schemas/byok-connection.schema.json').read_text())
    assert contract['properties']==ConnectionInput.model_json_schema()['properties']

def test_session_dispatch_cap_blocks_before_send(setup_byok):
    c,m,_,sent,_=setup_byok;a=start(c);connect(c,a);p=command(c,a)
    m.state(a).sends=20
    r=c.post('/api/v1/model-connection/test',headers=headers(a),json=p)
    assert r.status_code==429 and not sent
    assert c.get('/api/v1/model-connection',headers=headers(a)).status_code==200
    assert c.get('/api/v1/session-export',headers=headers(a)).status_code==200
