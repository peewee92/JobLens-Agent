"""Stable authorization conflict and deterministic command fingerprint."""
from hashlib import sha256
import json


class RequirementCallConflict(ValueError):
    pass


def digest(value):
    return sha256(json.dumps(value, sort_keys=True, ensure_ascii=False, separators=(",", ":")).encode()).hexdigest()
