"""Evidence-insufficient path with real matching and synthetic SQLite facts."""
from unittest.mock import Mock

from app.application.rule_match import _NoModel
from .test_career_agent_analysis_snapshot import synthetic_api, approve


def test_unrelated_confirmed_evidence_produces_real_insufficient_report(synthetic_api, monkeypatch):
    client, _, ids = synthetic_api
    forbidden = Mock(side_effect=AssertionError('no model call authorized'))
    monkeypatch.setattr(_NoModel, 'match', forbidden)
    profile = client.put('/api/v1/profile', json={
        'expectedVersion': 1, 'headline': 'Synthetic unrelated background', 'yearsOfExperience': 2,
        'evidence': [{'key': 'writing', 'type': 'project', 'summary': 'Edited a synthetic newsletter', 'source': 'Synthetic test'}],
        'skills': []})
    assert profile.status_code == 200, profile.text
    response = client.post(f'/api/v1/jobs/{ids[0]}/match-report')
    assert response.status_code == 200, response.text
    report = response.json()
    forbidden.assert_not_called()
    assert report['profileVersion'] == 2
    assert report['eligibility'] == 'conditional' and report['recommendation'] == 'low'
    assert report['requirementResults'][0]['semanticVerdict'] == 'not_matched'
    assert report['requirementResults'][0]['evidenceIds'] == []
    assert report['providerCalls'] == 0
    before = client.get(f'/api/v1/jobs/{ids[0]}/match-reports')
    assert before.status_code == 200, before.text
    old = next(x for x in before.json()['items'] if x['report']['profileVersion'] == 2)
    assert old['isCurrent'] is True
    preflight = client.get('/api/v1/match-ranking/preflight', params={'jobId': ids[0]})
    assert preflight.status_code == 200, preflight.text
    assert preflight.json()['items'][0]['targetCandidate'] is False
    assert preflight.json()['items'][0]['recommendation'] == 'low'
    updated = client.put('/api/v1/profile', json={
        'expectedVersion': 2, 'headline': 'Synthetic confirmed experience', 'yearsOfExperience': 2,
        'evidence': [{'key': 'python', 'type': 'project', 'summary': 'Built a Python backend', 'source': 'Synthetic test'}],
        'skills': [{'name': 'Python', 'level': 'working', 'evidenceKeys': ['python']}]})
    assert updated.status_code == 200, updated.text
    history = client.get(f'/api/v1/jobs/{ids[0]}/match-reports').json()['items']
    stale = next(x for x in history if x['report']['profileVersion'] == 2)
    assert stale['isCurrent'] is False
    assert stale['reportId'] == old['reportId']
    assert stale['report'] == old['report']
    assert 'profile_changed' in stale['staleReasons']
    recalculated = client.post(f'/api/v1/jobs/{ids[0]}/match-report')
    assert recalculated.status_code == 200, recalculated.text
    new = recalculated.json()
    assert new['profileVersion'] == 3 and new['providerCalls'] == 0
    assert new['recommendation'] == 'strong'
    assert new['requirementResults'][0]['semanticVerdict'] == 'matched'
    assert new['evidenceLinks'][0]['evidenceIds']
    history = client.get(f'/api/v1/jobs/{ids[0]}/match-reports').json()['items']
    assert any(x['reportId'] == old['reportId'] and not x['isCurrent'] for x in history)
    assert any(x['report']['profileVersion'] == 3 and x['isCurrent'] for x in history)
    state = client.post('/api/v1/career-agent/runs', json={
        'threadId': 'insufficient_then_confirmed', 'runId': 'run_insufficient_then_confirmed',
        'requestId': 'request_insufficient_then_confirmed', 'jobIds': ids[:1], 'topN': 1})
    assert state.status_code == 200, state.text
    assert state.json()['status'] == 'interrupted'
    completed = approve(client, state.json())
    assert completed.status_code == 200 and completed.json()['status'] == 'completed', completed.text
    saved = client.get('/api/v1/career-agent/runs/insufficient_then_confirmed/result')
    assert saved.status_code == 200 and saved.json()['profileVersion'] == 3
    assert saved.json()['selectedJobIds'] == ids[:1]
    forbidden.assert_not_called()
