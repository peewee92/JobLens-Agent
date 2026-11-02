"""One authorized real-posting extraction in a new private database; never auto-retries."""
import argparse
from hashlib import sha256
import json
import os
from pathlib import Path
import subprocess
import sys
import time


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--case', required=True, type=Path)
    parser.add_argument('--directory', required=True, type=Path)
    parser.add_argument('--confirm-live-cost', action='store_true')
    args = parser.parse_args()
    case = json.loads(args.case.read_text())
    if sha256(case['description'].encode()).hexdigest() != case['descriptionSha256'] or not case.get('humanExpectations'):
        raise ValueError('Must freeze posting hash and human expectations before observing model output')
    directory = args.directory.resolve()
    private_root = Path(__file__).resolve().parents[3] / 'data/private'
    if not directory.is_relative_to(private_root.resolve()):
        raise ValueError('Evidence must stay under ignored data/private')
    if not args.confirm_live_cost:
        print(json.dumps({'state': 'not_executed', 'providerCalls': 0})); return 0
    # Refuse reuse: timeout or lost receipt must not lead to another paid request.
    directory.mkdir(parents=True, exist_ok=False, mode=0o700)
    from app.core.config import get_settings
    settings = get_settings()
    from urllib.parse import urlsplit
    if settings.requirement_extractor_model != 'qwen3.8-flash' or not (urlsplit(settings.openai_base_url).hostname or '').endswith('.cn-beijing.maas.aliyuncs.com'):
        raise ValueError('This price verification applies only to the confirmed Beijing Qwen service')
    if not settings.openai_api_key:
        raise ValueError('No configured credential')
    # Official Beijing uncached price: CNY 0.8/M input, 2.7/M output.
    # Use 100K UTF-8 request bytes + 1024 as a conservative input allowance;
    # non-thinking output capped at 4096, no tools/cache creation/automatic retries.
    reserved = (101024 * .8 + 4096 * 2.7) / 1000000
    receipt = {'state': 'reserved', 'model': settings.requirement_extractor_model, 'inputCnyPerMillion': .8,
               'outputCnyPerMillion': 2.7, 'reservedCny': reserved, 'phaseLimitCny': 5,
               'totalLimitCny': 20, 'actualBilledCny': None, 'descriptionSha256': case['descriptionSha256'],
               'priceSource': 'https://help.aliyun.com/zh/model-studio/qwen3-8-flash', 'attempts': 0}
    import fcntl
    ledger_path = private_root / 'delivery-model-budget.json'
    with (private_root / 'delivery-model-budget.lock').open('a') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        if ledger_path.exists():
            ledger = json.loads(ledger_path.read_text())
        else:
            # Include previously recorded probes; unknown charges keep their reservation.
            ledger = {'reservations': {str(p.parent): json.loads(p.read_text()).get('reservedCny', 0)
                for p in private_root.glob('public-delivery-*/probe-*/receipt.json')}}
        total = sum(ledger['reservations'].values())
        if total + reserved > 5:
            raise RuntimeError('First-phase CNY 5 reservation budget exhausted; no request dispatched')
        ledger['reservations'][str(directory)] = reserved
        temporary = ledger_path.with_suffix('.tmp')
        temporary.write_text(json.dumps(ledger, indent=2))
        temporary.replace(ledger_path)
    receipt_path = directory/'receipt.json'
    def save(): receipt_path.write_text(json.dumps(receipt, ensure_ascii=False, indent=2))
    save()
    env = {**os.environ, 'DATABASE_URL': f'sqlite:///{directory / "acceptance.db"}'}
    with (directory/'migration.log').open('w') as log:
        subprocess.run([sys.executable, '-m', 'alembic', 'upgrade', 'head'], env=env, stdout=log, stderr=log, check=True)
    import httpx
    from sqlalchemy import create_engine
    from sqlalchemy.orm import sessionmaker
    from app.db.context import DatabaseContext, current_database
    from app.main import create_app
    from app.llm.authorized_requirement_factory import authorized_extractor_factory
    from fastapi.testclient import TestClient
    engine = create_engine(env['DATABASE_URL'], connect_args={'check_same_thread': False})
    context = DatabaseContext(engine, sessionmaker(bind=engine, autoflush=False), directory)
    configured = settings.model_copy(update={'requirement_extractor_enable_thinking': False,
        'requirement_extractor_max_completion_tokens': 4096, 'requirement_extractor_timeout_seconds': 60.0})
    class BudgetTransport(httpx.BaseTransport):
        def __init__(self): self.inner = httpx.HTTPTransport(retries=0)
        def handle_request(self, request):
            body = json.loads(request.content)
            if receipt['attempts'] or len(request.content) > 100000 or body.get('max_completion_tokens') != 4096 or body.get('enable_thinking') is not False or body.get('tools') or body.get('stream'):
                raise RuntimeError('Budget boundary refused dispatch')
            receipt['attempts'] = 1
            receipt['state'] = 'dispatched_unknown'
            save()  # Durable reservation before the actual network request.
            return self.inner.handle_request(request)
        def close(self): self.inner.close()
    app = create_app()
    @app.middleware('http')
    async def isolate(request, call_next):
        token = current_database.set(context)
        try: return await call_next(request)
        finally: current_database.reset(token)
    # Use the existing service factory's module seam; no separate extraction pipeline.
    import app.llm.authorized_requirement_factory as factory_module
    original_factory = factory_module.authorized_extractor_factory
    factory_module.authorized_extractor_factory = lambda s, journal: original_factory(configured, journal, BudgetTransport)
    started = time.monotonic()
    try:
        with TestClient(app) as client:
            imported = client.post('/api/v1/job-imports/manual', json={'title': 'Private real posting acceptance', 'company': 'Private source', 'description': case['description']})
            imported.raise_for_status(); job = imported.json()['jobId']
            plan = client.get(f'/api/v1/jobs/{job}/requirement-call-plan')
            plan.raise_for_status(); plan = plan.json()
            if not plan['available']: raise RuntimeError('Configured provider is not available')
            command = {'actionId': 'delivery-probe-1', 'planDigest': plan['planDigest'], 'confirmed': True, 'maxProviderCalls': 1}
            response = client.post(f'/api/v1/jobs/{job}/requirement-calls', json=command)
            (directory/'call-response.json').write_text(response.text)
            response.raise_for_status()
            record = response.json()
            receipt.update(state=record['status'], responseStatus=record.get('responseStatus'), attempts=record.get('attempts', receipt['attempts']),
                           inputTokens=record.get('inputTokens'), outputTokens=record.get('outputTokens'), elapsedSeconds=round(time.monotonic()-started, 3))
            if record.get('inputTokens') is not None and record.get('outputTokens') is not None:
                receipt['estimatedStandardCny'] = (record['inputTokens'] * .8 + record['outputTokens'] * 2.7) / 1000000
            facts = client.get(f'/api/v1/jobs/{job}/requirements')
            if facts.status_code == 200:
                (directory/'requirements.json').write_text(facts.text)
                receipt['requirementsProduced'] = len(facts.json().get('requirements', []))
            save()
    except Exception as exc:
        receipt['errorClass'] = type(exc).__name__  # Do not disclose provider output/credentials.
        receipt['elapsedSeconds'] = round(time.monotonic()-started, 3)
        save()
    finally:
        factory_module.authorized_extractor_factory = original_factory
        engine.dispose()
    print(json.dumps(receipt, ensure_ascii=False))
    return 0 if receipt.get('requirementsProduced') else 1


if __name__ == '__main__':
    raise SystemExit(main())
