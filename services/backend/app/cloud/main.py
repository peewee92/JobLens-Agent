"""Dedicated hosted private service. No local filesystem DB or implicit online model."""
from __future__ import annotations

import json
import os
from pathlib import Path

# Set mode before business imports. Tenant URL resolution has no fallback.
os.environ.update({
    "APP_ENV": "cloud",
    "DATABASE_URL": "sqlite:///:memory:",
    "JOBLENS_LOCAL_PRODUCT": "0",
    "CAREER_AGENT_CHECKPOINT_PATH": "/nonexistent/joblens-cloud-do-not-read",
    "OPENAI_API_KEY": "",
    "PROFILE_EXTRACTOR_PROVIDER": "disabled",
    "CAREER_INTENT_PROVIDER": "disabled",
    "REQUIREMENT_EXTRACTOR_PROVIDER": "disabled",
    "REQUIREMENT_EXTRACTOR_FALLBACK_PROVIDER": "disabled",
    "SEMANTIC_MATCH_PROVIDER": "disabled",
})

from sqlalchemy import create_engine
from sqlalchemy.engine import make_url
from sqlalchemy.orm import sessionmaker

from app.cloud.private_app import create_private_app
from app.cloud.postgres import verified_postgres
from app.db.context import DatabaseContext


def load_workspaces(raw: str) -> dict[str, DatabaseContext]:
    try:
        mapping = json.loads(raw)
        if not isinstance(mapping, dict) or not 1 <= len(mapping) <= 12:
            raise ValueError
        result = {}
        identities = set()
        for owner, value in mapping.items():
            url = make_url(value)
            if (url.drivername not in {"postgresql", "postgresql+psycopg"} or not url.host
                    or not url.database or url.database in {"postgres", "template0", "template1"}
                    or not url.username or url.query.get("sslmode") != "verify-full"
                    or set(url.query) - {"sslmode", "channel_binding"}
                    or "-pooler." in url.host.lower()):
                raise ValueError
            # A username or a different password is not a tenant boundary if both point to one DB.
            key = (url.host.lower(), url.port or 5432, url.database)
            if key in identities:
                raise ValueError
            identities.add(key)
            url = verified_postgres(url)
            engine = create_engine(url, pool_size=2, max_overflow=0, pool_pre_ping=True,
                                   pool_timeout=8, connect_args={"connect_timeout": 8}, hide_parameters=True)
            result[owner] = DatabaseContext(engine, sessionmaker(bind=engine, autoflush=False),
                                            Path("/nonexistent/joblens-cloud-do-not-read"))
        return result
    except Exception:
        raise RuntimeError("Invalid private workspace configuration; check dedicated TLS URLs and account mappings.") from None


app = create_private_app(load_workspaces(os.environ.get("JOBLENS_CLOUD_WORKSPACES", "")),
                         os.environ.get("JOBLENS_CLOUD_PROXY_SECRET", "").encode("utf-8"))
