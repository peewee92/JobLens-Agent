"""No seeded reports/baselines: confirmed user facts and three pasted jobs to action."""
from sqlalchemy import text
from .test_first_job_journey import first_user, save_inputs


def prepare(client, title, description):
    imported = client.post('/api/v1/job-imports/manual', json={
        'title':title, 'company':'合成闭环验收公司', 'description':description})
    assert imported.status_code == 201, imported.text
    job = imported.json()['jobId']
    extracted = client.post(f'/api/v1/jobs/{job}/requirement-extractions')
    assert extracted.status_code == 201, extracted.text
    facts = extracted.json()
    checked = client.post(f'/api/v1/jobs/{job}/requirement-confirmations', json={
        'actionId':f'check-{job}', 'extractionId':facts['extractionId'], 'inputHash':facts['inputHash'],
        'factsDigest':facts['factsDigest'], 'confirmed':True})
    assert checked.status_code == 200, checked.text
    matched = client.post(f'/api/v1/jobs/{job}/match-report')
    assert matched.status_code == 200, matched.text
    return job, matched.json()


def test_three_pasted_jobs_to_confirmed_targets_saved_materials_and_action(first_user):
    c, factory = first_user
    save_inputs(c, supported=True)
    first, supported = prepare(c, 'Python 后端工程师',
        '任职要求：熟练掌握 Python，能够说明真实的服务开发与维护经验。\n加分项：熟悉 Docker，并能够说明容器部署经验。')
    unknown, insufficient = prepare(c, 'TypeScript 工程师',
        '任职要求：熟练掌握 TypeScript，并能够说明真实的类型系统设计与工程维护经验。')
    conflict, blocked = prepare(c, '高级后端工程师',
        '任职要求：至少5年以上工作经验，能够以真实工作年限记录说明满足这一工作经验要求。')
    assert insufficient['recommendation'] == 'low'
    assert blocked['recommendation'] == 'blocked'
    ids = [first, unknown, conflict]
    start = c.post('/api/v1/career-agent/runs', json={'threadId':'three-job', 'runId':'three-run',
        'requestId':'three-request', 'jobIds':ids, 'topN':3})
    assert start.status_code == 200, start.text
    state = start.json()
    assert state['status'] == 'interrupted', state
    assert state['proposedTargetJobIds'] == [first], state
    decision = {'interruptId':state['interruptId'], 'actionId':'choose-target', 'decision':'approve'}
    completed = c.post('/api/v1/career-agent/runs/three-job/resume', json=decision)
    assert completed.status_code == 200, completed.text
    assert completed.json()['status'] == 'completed', completed.text
    result = c.get('/api/v1/career-agent/runs/three-job/result').json()
    assert result['selectedJobIds'] == [first] and result['isCurrent']
    assert result['preparations'][0]['factsUsable']
    assert result['preparations'][0]['interviewFacts']['items']
    assert c.get('/api/v1/career-agent/runs/three-job/result').json() == result
    command = {'commandId':'start-execution', 'resultId':result['resultId'], 'jobIds':[first]}
    path = '/api/v1/career-agent/runs/three-job/execution'
    executed = c.post(path, json=command)
    assert executed.status_code == 200, executed.text
    receipt = executed.json()
    assert c.post(path, json=command).json() == receipt
    workspace = receipt['items'][0]
    assert workspace['actionIds']
    root = '/api/v1/application-workspaces/'+workspace['workspaceId']
    assert c.get(root+'/preparation').json()['preparation'] == result['preparations'][0]
    action = c.post(root+'/actions/'+workspace['actionIds'][0]+'/status', json={
        'actorId':'local-user', 'expectedStatus':'todo', 'newStatus':'in_progress'})
    assert action.status_code == 200, action.text
    with factory() as session:
        assert session.execute(text('SELECT count(*) FROM user_profiles')).scalar_one() == 1
        assert session.execute(text('SELECT count(*) FROM match_reports')).scalar_one() == 3
        assert session.execute(text('SELECT count(*) FROM application_workspaces')).scalar_one() == 1
        assert session.execute(text('SELECT count(*) FROM requirement_review_batch_final_decisions')).scalar_one() == 0
        assert session.execute(text('SELECT count(*) FROM semantic_calls')).scalar_one() == 0
        assert session.execute(text('PRAGMA foreign_key_check')).all() == []


def test_no_reliable_targets_does_not_fill_top_three(first_user):
    c, factory = first_user
    save_inputs(c, supported=False)
    ids = [prepare(c, f'TypeScript 工程师 {n}',
        '任职要求：熟练掌握 TypeScript，并能够说明真实的类型系统设计与工程维护经验。')[0] for n in range(3)]
    response = c.post('/api/v1/career-agent/runs', json={'threadId':'no-target', 'runId':'no-target-run',
        'requestId':'no-target-request', 'jobIds':ids, 'topN':3})
    assert response.status_code == 200, response.text
    state = response.json()
    assert state['status'] == 'blocked' and state['currentStep'] == 'target_evidence_insufficient', state
    assert state['proposedTargetJobIds'] == [] and not state['pendingApproval']
    with factory() as session:
        assert session.execute(text('SELECT count(*) FROM application_workspaces')).scalar_one() == 0
        assert session.execute(text('SELECT count(*) FROM match_reports')).scalar_one() == 3
