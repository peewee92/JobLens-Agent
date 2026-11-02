"""Exactly one transport attempt, no retry, redirect, fallback or open transaction."""
from contextlib import contextmanager
import httpx
from app.llm.semantic_matchers import OpenAISemanticMatcher
from app.llm.journaled_requirement_transport import JournaledTransport


def authorized_semantic_factory(settings, journal, transport_factory=None):
    make_transport = transport_factory or (lambda: httpx.HTTPTransport(retries=0))

    @contextmanager
    def create(action_id, snapshot):
        with httpx.Client(transport=JournaledTransport(journal, action_id, make_transport()),
            timeout=snapshot["timeoutSeconds"], follow_redirects=False) as client:
            yield OpenAISemanticMatcher(api_key=settings.openai_api_key, model=snapshot["model"],
                base_url=settings.openai_base_url, api_style=settings.semantic_match_api_style,
                enable_thinking=settings.semantic_match_enable_thinking,
                max_completion_tokens=snapshot["maxOutputTokens"], timeout_seconds=snapshot["timeoutSeconds"], client=client)
    return create
