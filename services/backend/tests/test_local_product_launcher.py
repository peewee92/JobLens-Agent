import importlib.util
import json
from pathlib import Path
import sys
import pytest

SCRIPT_ROOT = Path(__file__).resolve().parents[3] / "scripts"
sys.path.insert(0, str(SCRIPT_ROOT))
import local as launcher


def test_local_environment_does_not_inherit_models_dbs_or_demo_mode(monkeypatch, tmp_path):
    for key in ["OPENAI_API_KEY", "PROFILE_EXTRACTOR_PROVIDER", "JOBLENS_PUBLIC_DEMO", "DATABASE_URL"]:
        monkeypatch.setenv(key, "private-old-value")
    env = launcher.environment(tmp_path, None, 8124, 3124)
    assert env["JOBLENS_LOCAL_PRODUCT"] == "1"
    assert env["JOBLENS_LOCAL_CONFIG"] == ""
    assert env["DATABASE_URL"] == f"sqlite:///{tmp_path / 'local.db'}"
    assert "OPENAI_API_KEY" not in env
    assert "PROFILE_EXTRACTOR_PROVIDER" not in env
    assert "JOBLENS_PUBLIC_DEMO" not in env
    assert "JOBLENS_DEMO" not in env


def test_launcher_only_accepts_empty_or_owned_local_data(tmp_path):
    path = launcher.protected_directory(tmp_path / "personal")
    assert json.loads((path / launcher.MARKER).read_text())["status"] == "initializing"
    with pytest.raises(RuntimeError):
        launcher.protected_directory(path)
    (path / launcher.DB_NAME).touch()
    (path / launcher.MARKER).write_text(json.dumps(launcher.DATA_VERSION))
    assert launcher.protected_directory(path) == path
    (tmp_path / "foreign").mkdir()
    (tmp_path / "foreign/demo.db").write_text("do not migrate")
    with pytest.raises(RuntimeError):
        launcher.protected_directory(tmp_path / "foreign")
    assert (tmp_path / "foreign/demo.db").read_text() == "do not migrate"


def test_launcher_rejects_symlink_and_missing_database(tmp_path):
    target = tmp_path / "target"
    target.mkdir()
    link = tmp_path / "link"
    link.symlink_to(target, target_is_directory=True)
    with pytest.raises(RuntimeError):
        launcher.protected_directory(link)
    (target / launcher.MARKER).write_text(json.dumps(launcher.DATA_VERSION))
    with pytest.raises(RuntimeError):
        launcher.protected_directory(target)
