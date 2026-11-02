"""Pasted jobs to human-confirmed feedback and saved update, without seeded reports."""
from sqlalchemy import text
from .test_first_job_journey import first_user, save_inputs
from .test_three_job_journey import prepare


def approve(client, thread, state, action):
    response = client.post(f'/api/v1/career-agent/runs/{thread}/resume', json={
        'interruptId':state['interruptId'], 'actionId':action, 'decision':'approve'})
    assert response.status_code == 200, response.text
    assert response.json()['status'] == 'completed', response.text


def test_completed_action_confirmed_fact_and_original_target_update(first_user):
    client, factory = first_user
    save_inputs(client, supported=True)
    job, _ = prepare(client, 'Python 后端工程师',
        '任职要求：熟练掌握 Python，能够说明真实的服务开发与维护经验。\n加分项：熟悉 Docker，并能够说明容器部署经验。')
    other, _ = prepare(client, 'TypeScript 工程师',
        '任职要求：熟练掌握 TypeScript，并能够说明真实的类型系统设计与工程维护经验。')
    conflict, _ = prepare(client, '高级后端工程师',
        '任职要求：至少5年以上工作经验，能够以真实工作年限记录说明满足这一工作经验要求。')
    base = '/api/v1/career-agent/runs/feedback-source'
    started = client.post('/api/v1/career-agent/runs', json=dict(threadId='feedback-source',
        runId='source-run', requestId='source-request', jobIds=[job,other,conflict], topN=3))
    assert started.status_code == 200, started.text
    approve(client, 'feedback-source', started.json(), 'accept-first')
    original = client.get(base+'/result').json()
    execution = client.post(base+'/execution', json=dict(commandId='execute-source', resultId=original['resultId'], jobIds=[job]))
    assert execution.status_code == 200, execution.text
    item = execution.json()['items'][0]
    root = '/api/v1/application-workspaces/'+item['workspaceId']
    preparation = client.get(root+'/preparation').json()['preparation']
    # The last generated preparation action covers all interview requirements.
    action = item['actionIds'][-1]
    for expected,new in [('todo','in_progress'),('in_progress','done')]:
        response = client.post(root+f'/actions/{action}/status', json=dict(actorId='local-user',expectedStatus=expected,newStatus=new))
        assert response.status_code == 200, response.text
    context = client.get(root+'/evidence-context').json()
    source = next(s for s in context['actionSources'] if s['actionId'] == action)
    requirement = next(r for r,name in source['options'] if name == 'Docker')
    assert client.get('/api/v1/profile').json()['version'] == 1
    body = dict(actorId='local-user', idempotencyKey='actual-docker-fact', evidenceType='project',
        evidenceSummary='完成合成服务的 Docker 构建、启动和检查，保留运行步骤。',
        evidenceSource='合成验收仓库及检查记录，不是真实职业经历', skillLevel='working',requirementId=requirement,
        expectedProfileId=context['currentProfileId'],expectedProfileVersion=1,reviewedCurrentProfile=True)
    response = client.post(root+f'/actions/{action}/evidence-proposals',json=body)
    assert response.status_code == 201, response.text
    proposal = response.json()
    overview = client.get(root+'/overview').json()
    assert overview['nextBestAction']['code'] == 'confirm_evidence', overview
    assert client.get('/api/v1/profile').json()['version'] == 1
    path = root+f"/evidence-proposals/{proposal['proposalId']}/confirm"
    confirmed = client.post(path,json={'actorId':'local-user'})
    assert confirmed.status_code == 200, confirmed.text
    assert client.get('/api/v1/profile').json()['version'] == 2
    assert client.post(path,json={'actorId':'local-user'}).json() == confirmed.json()
    old = client.get(base+'/result').json()
    assert not old['isCurrent'] and old['preparations'] == original['preparations']
    assert client.get(root+'/preparation').json()['preparation'] == preparation
    plan = client.get(base+'/update-plan?scope=targets').json()
    assert plan['profileVersion'] == 2 and [i['jobId'] for i in plan['items']] == [job]
    assert plan['items'][0]['status'] == 'ready', plan
    command = dict(threadId='feedback-update',runId='update-run',requestId='update-request',
        sourceResultId=original['resultId'],scope='targets',inputDigest=plan['inputDigest'],topN=3)
    updated = client.post(base+'/updates',json=command)
    assert updated.status_code == 200, updated.text
    approve(client,'feedback-update',updated.json(),'accept-update')
    current = '/api/v1/career-agent/runs/feedback-update'
    saved = client.get(current+'/result').json()
    assert saved['profileVersion'] == 2 and saved['resultId'] != original['resultId']
    response = client.get(current+'/comparison')
    assert response.status_code == 200, response.text
    compared = response.json()
    assert compared['requestedJobIds'] == [job] and compared['rankingComparable'], compared
    change = compared['items'][0]
    assert change['rankChange'] == 0 and change['previousRecommendation'] == change['currentRecommendation']
    docker = next(r for r in change['requirements'] if r['requirementId'] == requirement)
    assert (docker['previousCoverage'],docker['currentCoverage']) == ('unverified','supported'), docker
    assert docker['currentEvidenceIds'] and not docker['previousEvidenceIds']
    response = client.post(current+'/execution',json=dict(commandId='execute-update',resultId=saved['resultId'],jobIds=[job]))
    assert response.status_code == 200, response.text
    assert response.json()['items'][0]['workspaceId'] == item['workspaceId']
    assert client.get(root+'/preparation').json()['threadId'] == 'feedback-update'
    # Currentness is live metadata; the original saved payload is immutable.
    reopened = client.get(base+'/result').json()
    assert {k:v for k,v in reopened.items() if k != 'staleReasons'} == {k:v for k,v in old.items() if k != 'staleReasons'}
    assert client.get(current+'/comparison').json() == compared
    with factory() as session:
        for table,count in [('user_profiles',2),('application_workspaces',1),('match_reports',4),('requirement_calls',0),('semantic_calls',0)]:
            assert session.execute(text(f'SELECT count(*) FROM {table}')).scalar_one() == count
        assert session.execute(text('SELECT status FROM execution_action_items WHERE id=:id'),{'id':action}).scalar_one() == 'done'
        assert session.execute(text('PRAGMA foreign_key_check')).all() == []
