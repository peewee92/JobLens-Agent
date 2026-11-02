"""Read-only compatibility check; no analysis commands or external requests.

Run after verify_migration_copy against its migrated copy, not as model-quality evidence.
Only counts, HTTP statuses and reason codes are printed, never career facts or job IDs.
"""
from __future__ import annotations

import argparse
from collections import Counter
import json
import logging
import os
from pathlib import Path
import socket
from unittest.mock import patch


def audit(client) -> dict:
    checks = []
    blockers = Counter()
    semantic_reasons = Counter()
    compatible = True

    def read(path, *, label=None, params=None, missing_ok=False):
        nonlocal compatible
        response = client.get('/api/v1' + path, params=params)
        accepted = response.status_code == 200 or (missing_ok and response.status_code in {404, 409})
        compatible = compatible and accepted
        checks.append({'route': label or path, 'status': response.status_code})
        return response.json() if response.status_code == 200 else None

    readiness = read('/readiness')
    if not readiness or not readiness.get('ready'):
        return {'apiReadable': False, 'checks': checks, 'jobsChecked': 0}
    workbench = read('/workbench')
    read('/profile', missing_ok=True)
    read('/search-intent', missing_ok=True)
    read('/career-agent/runs')
    read('/workbench/workspaces')
    page = read('/jobs', params={'limit': 50}) or {}
    jobs = page.get('items', [])
    for job in jobs:
        for suffix in ('', '/requirements', '/match-input-readiness', '/eligibility', '/match-reports', '/requirement-call-plan', '/semantic-call-plan'):
            body = read('/jobs/' + job['id'] + suffix, label='/jobs/{id}' + suffix, missing_ok=True)
            if body and suffix == '/match-input-readiness':
                blockers.update(item['code'] for item in body.get('blockers', []))
            if body and suffix == '/semantic-call-plan' and body.get('blockerCode'):
                semantic_reasons.update([body['blockerCode']])
    ranking = read('/match-ranking/preflight', params=[('jobId', job['id']) for job in jobs]) if jobs else None
    omissions = Counter(item['reason'] for item in (ranking or {}).get('omissions', []))
    stale = Counter(reason for item in (ranking or {}).get('omissions', []) for reason in item.get('staleReasons', []))
    # Aggregate repeated routes; never include actual job IDs or response bodies.
    statuses = Counter((item['route'], item['status']) for item in checks)
    return {
        'apiReadable': compatible,
        'checks': [{'route': route, 'status': status, 'count': count} for (route, status), count in statuses.items()],
        'jobsTotal': page.get('total', 0), 'jobsChecked': len(jobs),
        'scopeLimited': page.get('total', 0) > len(jobs),
        'rankableJobs': len((ranking or {}).get('items', [])),
        'rankingOmissions': dict(omissions), 'staleReasons': dict(stale),
        'inputBlockers': dict(blockers),
        'semanticPlanReasons': dict(semantic_reasons),
        'nextActionCode': (workbench or {}).get('nextAction', {}).get('code'),
        'modelQualityVerified': False,
    }


def verify_reads(database: Path) -> dict:
    database = database.resolve()
    if not database.is_file():
        raise ValueError('Database must already exist; migrate an independent copy first')
    # URI mode=ro is enforced by SQLite, not merely a convention of this script.
    os.environ.update({
        'DATABASE_URL': 'sqlite:///' + database.as_uri() + '?mode=ro&uri=true',
        'APP_ENV': 'test', 'OPENAI_API_KEY': '',
        'OPENAI_BASE_URL': 'http://127.0.0.1:1/disabled',
        'CAREER_AGENT_CHECKPOINT_PATH': str(database.parent / 'unused-read-audit-checkpoint.db'),
    })
    for prefix in ('PROFILE_EXTRACTOR', 'REQUIREMENT_EXTRACTOR', 'SEMANTIC_MATCH', 'CAREER_INTENT', 'REQUIREMENT_EXTRACTOR_FALLBACK'):
        os.environ[prefix + '_PROVIDER'] = 'disabled'
    # Import only after isolation; invoke via a fresh CLI process, not a running server.
    from fastapi.testclient import TestClient
    from app.main import create_app

    attempts = 0

    def no_network(*args, **kwargs):
        nonlocal attempts
        attempts += 1
        raise OSError('External connections disabled during read audit')

    with patch.object(socket.socket, 'connect', no_network), patch.object(socket.socket, 'connect_ex', no_network):
        with TestClient(create_app(), raise_server_exceptions=False) as client:
            result = audit(client)
    result.update(readOnly=True, providersDisabled=True, networkAttempts=attempts)
    result['apiReadable'] = result['apiReadable'] and attempts == 0
    return result


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--database', required=True, type=Path)
    args = parser.parse_args()
    # Framework HTTP/exception logs may contain private identifiers or payloads.
    logging.disable(logging.CRITICAL)
    try:
        result = verify_reads(args.database)
    except Exception:
        parser.exit(1, 'Read audit failed; check the migrated copy and configuration. No career data printed.\n')
    print(json.dumps(result, ensure_ascii=False))
    if not result['apiReadable']:
        parser.exit(1)


if __name__ == '__main__':
    main()
