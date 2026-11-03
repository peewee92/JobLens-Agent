"""One import may contain multiple observations of the same canonical job."""
from copy import deepcopy
from .test_career_agent_analysis_snapshot import synthetic_api
from .test_job_import_api import load_report


def test_duplicate_observations_preserve_audit_items_but_share_job(synthetic_api):
    client, _, _ = synthetic_api
    report = load_report()
    report['jobs'].append(deepcopy(report['jobs'][0]))
    created = client.post('/api/v1/job-imports', json=report)
    assert created.status_code == 201, created.text
    assert created.json()['received'] == 2
    assert created.json()['created'] == 1 and created.json()['updated'] == 1
    detail = client.get(f"/api/v1/job-imports/{created.json()['importId']}")
    assert detail.status_code == 200, detail.text
    items = detail.json()['items']
    assert len(items) == 2 and items[0]['jobId'] == items[1]['jobId']
    assert [item['outcome'] for item in items] == ['created', 'updated']


def test_each_import_preserves_original_observation_without_public_raw_leak(synthetic_api):
    from sqlalchemy import select
    from app.db.models import JobImportItemORM, JobORM, JobSourceORM

    client, factory, _ = synthetic_api
    report = load_report()
    first = report['jobs'][0]
    first['description'] = '第一版岗位描述：' + '原始职责与要求。' * 8
    first['privateMarker'] = 'private-first-observation'
    second = deepcopy(first)
    second['description'] = '第二版简短信息'
    second['privateMarker'] = 'private-second-observation'
    report['jobs'].append(second)
    response = client.post('/api/v1/job-imports', json=report)
    assert response.status_code == 201, response.text
    import_id = response.json()['importId']
    detail = client.get(f'/api/v1/job-imports/{import_id}')
    assert detail.status_code == 200, detail.text
    assert 'private-first-observation' not in detail.text
    assert 'private-second-observation' not in detail.text
    with factory() as session:
        items = session.scalars(select(JobImportItemORM).where(
            JobImportItemORM.import_id == import_id).order_by(JobImportItemORM.input_index)).all()
        assert len(items) == 2
        assert [item.source_raw_snapshot for item in items] == [first, second]
        assert items[0].job_id == items[1].job_id
        assert session.get(JobORM, items[0].job_id).description == second['description']
        assert session.get(JobSourceORM, items[0].job_source_id).source_raw == second


def test_reimport_observations_are_not_rewritten_and_errors_remain_private(synthetic_api):
    from sqlalchemy import select
    from app.db.models import JobImportItemORM

    client, factory, _ = synthetic_api
    report = load_report()
    report['jobs'][0]['privateMarker'] = 'first-hidden-marker'
    first = client.post('/api/v1/job-imports', json=report)
    assert first.status_code == 201
    job_id = client.get(f"/api/v1/job-imports/{first.json()['importId']}").json()['items'][0]['jobId']
    marked = client.put(f'/api/v1/jobs/{job_id}/user-availability', json={
        'userMarkedInactive': True, 'expectedRevision': 0})
    assert marked.status_code == 200
    second_report = deepcopy(report)
    second_report['jobs'][0]['privateMarker'] = 'second-hidden-marker'
    broken = deepcopy(second_report['jobs'][0])
    del broken['company']
    broken['privateMarker'] = 'error-hidden-marker'
    second_report['jobs'].append(broken)
    second = client.post('/api/v1/job-imports', json=second_report)
    assert second.status_code == 201
    assert client.get(f'/api/v1/jobs/{job_id}').json()['userMarkedInactive'] is True
    detail = client.get(f"/api/v1/job-imports/{second.json()['importId']}")
    assert all(marker not in detail.text for marker in ['second-hidden-marker', 'error-hidden-marker'])
    with factory() as session:
        old = session.scalar(select(JobImportItemORM).where(JobImportItemORM.import_id == first.json()['importId']))
        new = session.scalars(select(JobImportItemORM).where(JobImportItemORM.import_id == second.json()['importId']).order_by(JobImportItemORM.input_index)).all()
        assert old.source_raw_snapshot == report['jobs'][0]
        assert [item.source_raw_snapshot for item in new] == second_report['jobs']


def test_description_observations_are_scoped_bounded_and_do_not_expose_raw_fields(synthetic_api):
    import json
    from pathlib import Path
    from jsonschema import Draft202012Validator, FormatChecker
    from sqlalchemy import select
    from app.db.models import JobImportItemORM

    client, factory, _ = synthetic_api
    report = load_report()
    first = report['jobs'][0]
    first['description'] = '原始完整描述' * 10
    first['privateMarker'] = 'DO-NOT-EXPOSE'
    second = deepcopy(first)
    second['description'] = '较短描述'
    report['jobs'].append(second)
    response = client.post('/api/v1/job-imports', json=report)
    assert response.status_code == 201
    items = client.get(f"/api/v1/job-imports/{response.json()['importId']}").json()['items']
    job_id = items[0]['jobId']
    history = client.get(f'/api/v1/jobs/{job_id}/description-observations')
    assert history.status_code == 200, history.text
    assert 'DO-NOT-EXPOSE' not in history.text
    body = history.json()
    schema = json.loads((Path(__file__).resolve().parents[3] / 'packages/contracts/schemas/job-description-observations.schema.json').read_text())
    Draft202012Validator(schema, format_checker=FormatChecker()).validate(body)
    assert body['jobId'] == job_id and body['hasMore'] is False
    assert [x['description'] for x in body['items']] == ['较短描述', '原始完整描述' * 10]
    assert all(set(x) == {'importId', 'inputIndex', 'recordedAt', 'description', 'truncated'} for x in body['items'])
    assert client.get('/api/v1/jobs/job_does_not_exist/description-observations').status_code == 404

    with factory.begin() as session:
        old = session.scalar(select(JobImportItemORM).where(JobImportItemORM.import_id == response.json()['importId'], JobImportItemORM.input_index == 0))
        old.source_raw_snapshot = None
    body = client.get(f'/api/v1/jobs/{job_id}/description-observations').json()
    assert body['items'][1]['description'] is None  # Historical evidence was not backfilled.


def test_description_observations_limit_and_truncate(synthetic_api):
    client, factory, _ = synthetic_api
    report = load_report()
    report['jobs'] = [deepcopy(report['jobs'][0]) for _ in range(12)]
    response = client.post('/api/v1/job-imports', json=report)
    assert response.status_code == 201
    item = client.get(f"/api/v1/job-imports/{response.json()['importId']}").json()['items'][0]
    from sqlalchemy import select
    from app.db.models import JobImportItemORM
    with factory.begin() as session:
        row = session.scalar(select(JobImportItemORM).where(JobImportItemORM.import_id == response.json()['importId'], JobImportItemORM.input_index == 11))
        row.source_raw_snapshot = {'description': '字' * 50001, 'privateMarker': 'not-public'}
    body = client.get(f"/api/v1/jobs/{item['jobId']}/description-observations").json()
    assert body['hasMore'] is True and len(body['items']) == 10
    assert body['items'][0]['truncated'] and len(body['items'][0]['description']) == 50000
