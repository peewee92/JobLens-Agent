"""Dry-run safety only: these tests must never call a Provider."""
from hashlib import sha256
import json
from pathlib import Path
import subprocess
import sys


def test_dry_run_freezes_inputs_but_never_creates_database_or_calls_provider(tmp_path):
    case = tmp_path/'case.json'
    case.write_text(json.dumps({'description': 'Synthetic dry-run only',
        'descriptionSha256': sha256(b'Synthetic dry-run only').hexdigest(),
        'humanExpectations': {'mustNotInvent': ['Anything']}}))
    destination = Path(__file__).parents[3]/'data/private/unexecuted-dry-run-test'
    assert not destination.exists()
    result = subprocess.run([sys.executable, '-m', 'scripts.run_delivery_model_probe', '--case', str(case),
        '--directory', str(destination)], text=True, capture_output=True)
    assert result.returncode == 0, result.stderr
    assert json.loads(result.stdout) == {'state': 'not_executed', 'providerCalls': 0}
    assert not destination.exists()


def test_probe_refuses_mutated_inputs_before_any_dispatch(tmp_path):
    case = tmp_path/'case.json'
    case.write_text(json.dumps({'description': 'changed', 'descriptionSha256': '0'*64, 'humanExpectations': {'mustCapture': ['Fact']}}))
    result = subprocess.run([sys.executable, '-m', 'scripts.run_delivery_model_probe', '--case', str(case),
        '--directory', str(tmp_path/'output')], text=True, capture_output=True)
    assert result.returncode != 0
    assert not (tmp_path/'output').exists()
