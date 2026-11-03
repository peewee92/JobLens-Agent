"""Request-local model configuration; credentials never enter persistent state."""
from contextvars import ContextVar
from dataclasses import dataclass, field
from threading import RLock
from pydantic import BaseModel, ConfigDict, Field, SecretStr
from app.core.config import get_settings

class ConnectionInput(BaseModel):
    model_config = ConfigDict(extra='forbid')
    name: str = Field(default='我的模型', min_length=1, max_length=80)
    baseUrl: str = Field(min_length=8, max_length=1024)
    apiKey: SecretStr = Field(min_length=1, max_length=4096)
    model: str = Field(min_length=1, max_length=160, pattern=r'^\S(?:[^\r\n]*\S)?$')
    enableThinking: bool | None = None
    apiStyle: str = Field(default='chat_completions', pattern=r'^(chat_completions|responses)$')
    profileModel: str | None = Field(default=None, min_length=1, max_length=160)
    requirementModel: str | None = Field(default=None, min_length=1, max_length=160)
    semanticModel: str | None = Field(default=None, min_length=1, max_length=160)

@dataclass
class ModelSession:
    mode: str = 'sample'
    seed: str = 'sample'
    connection: ConnectionInput | None = field(default=None, repr=False)
    version: int = 0
    busy: bool = False
    importing: bool = False
    sends: int = 0
    lock: RLock = field(default_factory=RLock, repr=False)
    # Short-lived plans and results. No provider response body/exception text is recorded.
    plans: dict = field(default_factory=dict, repr=False)
    calls: dict = field(default_factory=dict, repr=False)

current_model: ContextVar[ModelSession | None] = ContextVar('joblens_model_session', default=None)

def model_settings(base=None):
    base = base if base is not None else get_settings()
    state = current_model.get()
    if state is None or state.mode != 'byok':
        return base
    with state.lock:
        c = state.connection
        values = dict(openai_api_key=c.apiKey.get_secret_value() if c else '',
                      openai_base_url=c.baseUrl if c else 'https://unconfigured.invalid/v1',
                      byok_connection_version=str(state.version),
                      requirement_extractor_fallback_provider='disabled', career_intent_provider='disabled')
        for task, model in [('profile_extractor', c.profileModel if c else None),
                            ('requirement_extractor', c.requirementModel if c else None),
                            ('semantic_match', c.semanticModel if c else None)]:
            values.update({f'{task}_provider': 'openai', f'{task}_model': model or (c.model if c else ''),
                           f'{task}_api_style': c.apiStyle if c else 'chat_completions',
                           f'{task}_enable_thinking': c.enableThinking if c else None, f'{task}_max_completion_tokens': 4096,
                           f'{task}_timeout_seconds': 60.})
        return base.model_copy(update=values)
