"""Real SQLite and HTTP: a scoped user decision, not a formal quality baseline."""
from concurrent.futures import ThreadPoolExecutor
from sqlalchemy import text
import pytest

from .test_career_agent_analysis_snapshot import synthetic_api


def _remove_baseline(factory):
    with factory.begin() as session:
        session.execute(text("DELETE FROM requirement_review_batch_final_decisions"))
        session.execute(text("DELETE FROM match_reports"))


def _command(client, job_id, action_id="confirm-one-posting"):
    extraction = client.get(f"/api/v1/jobs/{job_id}/requirements").json()
    assert extraction.get("factsDigest"), extraction
    return {"actionId": action_id, "extractionId": extraction["extractionId"],
        "inputHash": extraction["inputHash"], "factsDigest": extraction["factsDigest"], "confirmed": True}


def test_single_confirmation_unblocks_matching_not_other_jobs_or_formal_quality(synthetic_api):
    client, factory, ids = synthetic_api
    _remove_baseline(factory)
    path = f"/api/v1/jobs/{ids[0]}"
    assert not client.get(path + "/match-input-readiness").json()["inputsReleaseEligible"]
    payload = _command(client, ids[0])
    confirmed = client.post(path + "/requirement-confirmations", json=payload)
    assert confirmed.status_code == 200, confirmed.text
    assert client.post(path + "/requirement-confirmations", json=payload).json() == confirmed.json()
    readiness = client.get(path + "/match-input-readiness").json()
    assert readiness["inputsReleaseEligible"]
    assert readiness["jobRequirements"]["userConfirmationId"] == payload["actionId"]
    assert readiness["jobRequirements"]["acceptedBaselineDecisionId"] is None
    assert not client.get(f"/api/v1/jobs/{ids[1]}/match-input-readiness").json()["inputsReleaseEligible"]
    assert not client.get(path + "/requirement-release-readiness").json()["releaseEligible"]
    response = client.post(path + "/match-report")
    assert response.status_code == 200, response.text
    assert response.json()["providerCalls"] == 0
    assert response.json()["evidenceLinks"]
    assert client.get(path + "/match-reports").json()["items"][0]["report"]["jobId"] == ids[0]
    with factory() as session:
        assert session.execute(text("SELECT COUNT(*) FROM job_requirement_confirmations")).scalar_one() == 1
        assert session.execute(text("SELECT COUNT(*) FROM requirement_review_batch_final_decisions")).scalar_one() == 0


def test_same_action_different_facts_is_a_conflict(synthetic_api):
    client, factory, ids = synthetic_api
    _remove_baseline(factory)
    payload = _command(client, ids[0])
    assert client.post(f"/api/v1/jobs/{ids[0]}/requirement-confirmations", json=payload).status_code == 200
    different = _command(client, ids[1])
    response = client.post(f"/api/v1/jobs/{ids[1]}/requirement-confirmations", json=different)
    assert response.status_code == 409
    assert response.json()["error"]["code"] == "confirmation_action_conflict"


@pytest.mark.parametrize("change", ["description", "trace", "requirements", "inactive"])
def test_stale_or_invalid_facts_cannot_be_confirmed(synthetic_api, change):
    client, factory, ids = synthetic_api
    _remove_baseline(factory)
    payload = _command(client, ids[0])
    with factory.begin() as session:
        if change == "description":
            session.execute(text("UPDATE jobs SET description='different description' WHERE id=:id"), {"id": ids[0]})
        elif change == "trace":
            session.execute(text("UPDATE trace_spans SET error='failed' WHERE id=(SELECT trace_run_id FROM job_requirement_extractions WHERE job_id=:id)"), {"id": ids[0]})
        elif change == "requirements":
            session.execute(text("UPDATE job_requirements SET original_text='changed facts' WHERE job_id=:id"), {"id": ids[0]})
        else:
            session.execute(text("UPDATE jobs SET user_marked_inactive=1 WHERE id=:id"), {"id": ids[0]})
    response = client.post(f"/api/v1/jobs/{ids[0]}/requirement-confirmations", json=payload)
    assert response.status_code == 409, response.text
    with factory() as session:
        assert session.execute(text("SELECT COUNT(*) FROM job_requirement_confirmations")).scalar_one() == 0


def test_confirmation_save_failure_rolls_back_and_same_request_can_retry(synthetic_api):
    client, factory, ids = synthetic_api
    _remove_baseline(factory)
    payload = _command(client, ids[0])
    path = f"/api/v1/jobs/{ids[0]}/requirement-confirmations"
    with factory.begin() as session:
        session.execute(text("CREATE TRIGGER stop_confirmation BEFORE INSERT ON job_requirement_confirmations BEGIN SELECT RAISE(ABORT, 'test failure'); END"))
    assert client.post(path, json=payload).status_code == 503
    with factory.begin() as session:
        assert session.execute(text("SELECT COUNT(*) FROM job_requirement_confirmations")).scalar_one() == 0
        session.execute(text("DROP TRIGGER stop_confirmation"))
    assert client.post(path, json=payload).status_code == 200


def test_two_identical_confirmations_commit_one_record(synthetic_api):
    client, factory, ids = synthetic_api
    _remove_baseline(factory)
    payload = _command(client, ids[0])
    path = f"/api/v1/jobs/{ids[0]}/requirement-confirmations"
    with ThreadPoolExecutor(max_workers=2) as pool:
        responses = list(pool.map(lambda _: client.post(path, json=payload), range(2)))
    assert [response.status_code for response in responses] == [200, 200]
    assert responses[0].json() == responses[1].json()
    with factory() as session:
        assert session.execute(text("SELECT COUNT(*) FROM job_requirement_confirmations")).scalar_one() == 1


def test_confirmation_does_not_follow_mutated_output_even_if_trace_is_changed_too(synthetic_api):
    client, factory, ids = synthetic_api
    _remove_baseline(factory)
    path = f"/api/v1/jobs/{ids[0]}"
    payload = _command(client, ids[0])
    assert client.post(path + "/requirement-confirmations", json=payload).status_code == 200
    with factory.begin() as session:
        session.execute(text("UPDATE job_requirements SET original_text='changed facts' WHERE job_id=:id"), {"id": ids[0]})
        session.execute(text("UPDATE trace_spans SET output=json_set(output, '$.requirements[0].originalText', 'changed facts') WHERE id=(SELECT trace_run_id FROM job_requirement_extractions WHERE job_id=:id)"), {"id": ids[0]})
    current = client.get(path + "/match-input-readiness").json()
    assert not current["inputsReleaseEligible"]
    assert current["jobRequirements"]["userConfirmationId"] is None
    assert _command(client, ids[0])["factsDigest"] != payload["factsDigest"]


def test_user_must_explicitly_confirm(synthetic_api):
    client, factory, ids = synthetic_api
    _remove_baseline(factory)
    payload = _command(client, ids[0])
    payload["confirmed"] = False
    assert client.post(f"/api/v1/jobs/{ids[0]}/requirement-confirmations", json=payload).status_code == 422
    with factory() as session:
        assert session.execute(text("SELECT COUNT(*) FROM job_requirement_confirmations")).scalar_one() == 0


def test_confirmation_contracts_match_python_models():
    import json
    from pathlib import Path
    from app.api.v1.schemas.job_requirements import JobRequirementConfirmationRequest, JobRequirementConfirmationResponse
    root = Path(__file__).resolve().parents[3] / "packages/contracts/schemas"
    for name, model in (("job-requirement-confirmation-request", JobRequirementConfirmationRequest),
                        ("job-requirement-confirmation-response", JobRequirementConfirmationResponse)):
        schema = json.loads((root / f"{name}.schema.json").read_text())
        schema.pop("$schema")
        assert schema == model.model_json_schema(by_alias=True)
