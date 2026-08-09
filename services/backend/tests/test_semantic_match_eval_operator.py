"""Operator safety tests for Semantic Match quality evaluation."""
from __future__ import annotations

import pytest

from scripts.run_semantic_match_eval import resolve_eval_mode


def test_fixture_eval_does_not_require_live_cost_confirmation() -> None:
    assert resolve_eval_mode("fixture", confirm_live_cost=False) == "fixture"


def test_live_eval_requires_explicit_cost_confirmation() -> None:
    with pytest.raises(ValueError, match="confirm-live-cost"):
        resolve_eval_mode("openai", confirm_live_cost=False)

    assert resolve_eval_mode("openai", confirm_live_cost=True) == "live"


def test_disabled_provider_cannot_run_match_eval() -> None:
    with pytest.raises(ValueError, match="fixture or openai"):
        resolve_eval_mode("disabled", confirm_live_cost=False)
