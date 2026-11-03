"""Public command migrates and seeds a disposable DB, never the configured user DB."""
import importlib.util
import json
from pathlib import Path
import socket
import sqlite3
import pytest

ROOT = Path(__file__).parents[3]
spec = importlib.util.spec_from_file_location('product_demo_launcher', ROOT / 'scripts/demo.py')
demo = importlib.util.module_from_spec(spec)
spec.loader.exec_module(demo)


def counts(path):
    with sqlite3.connect(path) as connection:
        return {t:connection.execute(f'SELECT count(*) FROM {t}').fetchone()[0] for t in (
            'user_profiles','search_intents','jobs','match_reports','career_agent_runs','application_workspaces',
            'requirement_calls','semantic_calls','requirement_review_batch_final_decisions')}


def test_prepare_demo_uses_real_commands_and_resume_never_reseeds(tmp_path, monkeypatch):
    private = tmp_path / 'private.db'
    private.write_bytes(b'private sentinel: must never be opened or migrated')
    monkeypatch.setenv('DATABASE_URL',f'sqlite:///{private}')
    monkeypatch.setenv('OPENAI_API_KEY','do-not-use')
    monkeypatch.setenv('SEMANTIC_MATCH_PROVIDER','openai')
    directory = tmp_path / 'demo'
    demo.prepare_demo(directory)
    expected = dict(user_profiles=1,search_intents=1,jobs=3,match_reports=3,career_agent_runs=0,
        application_workspaces=0,requirement_calls=0,semantic_calls=0,requirement_review_batch_final_decisions=0)
    assert counts(directory / 'demo.db') == expected
    demo.prepare_demo(directory)
    assert counts(directory / 'demo.db') == expected
    assert private.read_bytes() == b'private sentinel: must never be opened or migrated'
    with sqlite3.connect(directory / 'demo.db') as connection:
        assert connection.execute('PRAGMA integrity_check').fetchone()[0] == 'ok'
        assert connection.execute('PRAGMA foreign_key_check').fetchall() == []
        assert {r[0] for r in connection.execute('SELECT recommendation FROM match_reports')} == {'strong','low','blocked'}


def test_empty_demo_and_non_owned_or_interrupted_directory_are_protected(tmp_path):
    empty = tmp_path / 'empty'
    demo.prepare_demo(empty,empty=True)
    assert not any(counts(empty / 'demo.db').values())
    with pytest.raises(RuntimeError): demo.prepare_demo(empty)
    other = tmp_path / 'other'; other.mkdir(); (other / 'demo.db').write_bytes(b'unchanged')
    with pytest.raises(RuntimeError): demo.prepare_demo(other)
    assert (other / 'demo.db').read_bytes() == b'unchanged'
    interrupted = tmp_path / 'interrupted'; interrupted.mkdir()
    (interrupted / demo.MARKER).write_text(json.dumps(dict(kind='joblens-synthetic-demo',version=1,status='initializing',empty=False)))
    with pytest.raises(RuntimeError): demo.prepare_demo(interrupted)


def test_model_settings_are_overridden_and_occupied_port_is_not_taken(tmp_path,monkeypatch):
    monkeypatch.setenv('REQUIREMENT_EXTRACTOR_PROVIDER','openai')
    monkeypatch.setenv('CAREER_INTENT_PROVIDER','openai')
    env = demo.demo_environment(tmp_path)
    assert env['REQUIREMENT_EXTRACTOR_PROVIDER'] == 'fixture'
    assert env['SEMANTIC_MATCH_PROVIDER'] == env['CAREER_INTENT_PROVIDER'] == env['PROFILE_EXTRACTOR_PROVIDER'] == 'disabled'
    assert env['REQUIREMENT_EXTRACTOR_FALLBACK_PROVIDER'] == 'disabled' and env['OPENAI_API_KEY'] == ''
    with socket.socket() as occupied:
        occupied.bind(('127.0.0.1',0))
        with pytest.raises(RuntimeError,match='已被占用'): demo.check_ports(occupied.getsockname()[1])
    with pytest.raises(RuntimeError): demo.check_ports(8100,8100)


def test_immediate_restart_accepts_recently_closed_listener():
    with socket.socket() as server:
        server.setsockopt(socket.SOL_SOCKET,socket.SO_REUSEADDR,1)
        server.bind(('127.0.0.1',0)); server.listen()
        port = server.getsockname()[1]
        with socket.create_connection(('127.0.0.1',port)) as client:
            connection,_ = server.accept()
            connection.close()
            assert client.recv(1) == b''
    demo.check_ports(port)  # TIME_WAIT is not a different running application.


def test_generated_demo_types_do_not_modify_regular_web_config(tmp_path,monkeypatch):
    config = tmp_path / 'tsconfig.json'
    config.write_text(json.dumps({'compilerOptions':{'strict':True},'include':['.next/types/**/*.ts']}))
    original = config.read_bytes()
    monkeypatch.setattr(demo,'WEB',tmp_path)
    demo.prepare_web_types(3100)
    generated = tmp_path / '.tsconfig-demo-3100.json'
    assert generated.is_file() and config.read_bytes() == original
    assert json.loads(generated.read_text())['compilerOptions']['strict']
    generated.write_text('{"preserve":"generated changes"}')
    demo.prepare_web_types(3100)
    assert generated.read_text() == '{"preserve":"generated changes"}'
