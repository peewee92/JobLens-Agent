"""Local compatibility diagnostics must neither write data nor contact providers."""
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import sys

import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.exc import OperationalError
from sqlalchemy.orm import sessionmaker

from app.db.base import Base
from app.db.models import CareerAgentRunORM, CareerAgentRunEventORM
from app.repositories.sqlalchemy_career_agent_checkpoint import SqlAlchemyCareerAgentCheckpointStore

BACKEND = Path(__file__).parents[1]
spec = importlib.util.spec_from_file_location('read_audit_demo', BACKEND.parents[1] / 'scripts/demo.py')
demo = importlib.util.module_from_spec(spec)
spec.loader.exec_module(demo)


def run_audit(path, env=None):
    return subprocess.run([sys.executable, '-m', 'scripts.verify_main_flow_reads', '--database', str(path)],
        cwd=BACKEND, env=env, capture_output=True, text=True)


def test_seeded_data_is_readable_without_mutation_or_private_output(tmp_path):
    directory = tmp_path / 'demo'
    demo.prepare_demo(directory)
    database = directory / 'demo.db'
    original = database.read_bytes()
    sentinel = tmp_path / 'private.db'
    sentinel.write_bytes(b'never open configured private database')
    result = run_audit(database, {**os.environ, 'DATABASE_URL': f'sqlite:///{sentinel}',
        'OPENAI_API_KEY': 'secret-key-sentinel', 'SEMANTIC_MATCH_PROVIDER': 'openai'})
    assert result.returncode == 0, result.stderr
    body = json.loads(result.stdout)
    assert body['apiReadable'] and body['readOnly'] and body['providersDisabled']
    assert body['networkAttempts'] == 0 and body['modelQualityVerified'] is False
    assert body['jobsChecked'] == 3 and body['rankableJobs'] == 2
    assert body['rankingOmissions'] == {'hard_conflict': 1}
    assert not body['scopeLimited']
    assert database.read_bytes() == original
    assert sentinel.read_bytes() == b'never open configured private database'
    assert 'secret-key-sentinel' not in result.stdout + result.stderr
    assert all('job_' not in check['route'] for check in body['checks'])
    assert not (directory / 'unused-read-audit-checkpoint.db').exists()


def test_missing_and_unmigrated_database_stop_without_creating_or_upgrading(tmp_path):
    path = tmp_path / 'missing.db'
    missing = run_audit(path)
    assert missing.returncode == 1 and not path.exists()
    path.touch()
    result = run_audit(path)
    assert result.returncode == 1
    body = json.loads(result.stdout)
    assert body['apiReadable'] is False and body['jobsChecked'] == 0
    assert body['checks'] == [{'route': '/readiness', 'status': 503}]
    assert path.read_bytes() == b''


def test_checkpoint_reads_accept_readonly_uri_and_database_rejects_writes(tmp_path):
    path = tmp_path / 'space #数据.db'
    writer = create_engine(f'sqlite:///{path}')
    Base.metadata.create_all(writer, tables=[CareerAgentRunORM.__table__, CareerAgentRunEventORM.__table__])
    writer.dispose()
    before = path.read_bytes()
    engine = create_engine('sqlite:///' + path.as_uri() + '?mode=ro&uri=true')
    try:
        store = SqlAlchemyCareerAgentCheckpointStore(sessionmaker(bind=engine))
        assert store.recent_runs() == ()
        with engine.connect() as connection, pytest.raises(OperationalError, match='readonly'):
            connection.execute(text('CREATE TABLE must_not_be_created (id INTEGER)'))
    finally:
        engine.dispose()
    assert path.read_bytes() == before
