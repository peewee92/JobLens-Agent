"""Private database connections verify the host using a portable public CA bundle."""
from __future__ import annotations

import certifi
from sqlalchemy.engine import URL


def verified_postgres(url: URL) -> URL:
    # Some binary libpq builds look in a bundled OpenSSL path instead of the OS trust store.
    return url.set(drivername="postgresql+psycopg").update_query_dict({
        "sslmode": "verify-full", "sslrootcert": certifi.where(),
    })
