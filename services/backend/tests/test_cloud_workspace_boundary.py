from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
import time

from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.cloud.boundary import identity_signature
from app.cloud.private_app import create_private_app
from app.db.context import DatabaseContext, current_database
from app.db.base import Base


SECRET = b"test-only-private-workspace-secret-not-deployed"


def signed(owner: str, path: str, *, method: str = "GET", issued: int | None = None) -> dict[str, str]:
    stamp = str(int(time.time()) if issued is None else issued)
    return {
        "x-joblens-owner": owner,
        "x-joblens-issued": stamp,
        "x-joblens-workspace-signature": identity_signature(SECRET, owner, stamp, method, path),
    }


def context(tmp_path: Path, name: str) -> DatabaseContext:
    engine = create_engine(f"sqlite:///{tmp_path / (name + '.db')}")
    Base.metadata.create_all(engine)
    return DatabaseContext(engine, sessionmaker(bind=engine), tmp_path)


def test_verified_accounts_cannot_read_or_modify_each_others_records(tmp_path):
    a, b = context(tmp_path, "alpha"), context(tmp_path, "beta")
    path = "/api/v1/profile"
    app = create_private_app({"account-alpha": a, "account-beta": b}, SECRET)
    with TestClient(app) as client:
        assert client.get("/api/v1/health").status_code == 200
        assert client.get(path).status_code == 401
        assert client.get(path, headers=signed("not-invited", path)).status_code == 403
        assert client.get(path, headers=signed("account-alpha", path, issued=int(time.time()) - 60)).status_code == 401
        assert client.get(path + "?actorId=account-beta", headers=signed("account-alpha", path)).status_code == 401
        assert client.get(path, headers={**signed("account-alpha", path), "x-joblens-owner": "account-beta"}).status_code == 401

        for owner, title in [("account-alpha", "Synthetic profile A"), ("account-beta", "Synthetic profile B")]:
            response = client.put(path, headers=signed(owner, path, method="PUT"),
                                  json={"expectedVersion": 0, "headline": title, "evidence": [], "skills": []})
            assert response.status_code == 200
            assert response.headers["cache-control"] == "private, no-store"

        with ThreadPoolExecutor(2) as threads:
            def read(owner: str) -> str:
                response = client.get(path, headers=signed(owner, path))
                assert response.status_code == 200
                return response.json()["headline"]
            assert list(threads.map(read, ("account-alpha", "account-beta"))) == ["Synthetic profile A", "Synthetic profile B"]

        # Even trusted forwarding cannot enable maintenance or unguarded demo endpoints.
        for p in ("/docs", "/api/v1/profile-evals", "/api/v1/demo/session", "/api/v1/local/profile-model/status"):
            assert client.get(p, headers=signed("account-alpha", p)).status_code == 404
        assert current_database.get() is None

    # A new service instance reads the same persistent, distinct databases.
    with TestClient(create_private_app({"account-alpha": a, "account-beta": b}, SECRET)) as restarted:
        assert restarted.get(path, headers=signed("account-alpha", path)).json()["headline"] == "Synthetic profile A"
        assert restarted.get(path, headers=signed("account-beta", path)).json()["headline"] == "Synthetic profile B"
