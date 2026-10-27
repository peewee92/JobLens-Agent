"""Preference facts shared by eligibility, semantic matching, and saved reports."""
from app.api.v1.schemas.common import CamelCaseModel
from app.application.search_preferences import PreferenceCheck


class PreferenceCheckResponse(CamelCaseModel):
    key: str
    status: str
    code: str
    reason: str
    intent_fields: list[str]
    job_fields: list[str]

    @classmethod
    def from_detail(cls, item: PreferenceCheck) -> "PreferenceCheckResponse":
        return cls(key=item.key, status=item.status.value, code=item.code,
                   reason=item.reason, intent_fields=list(item.intent_fields),
                   job_fields=list(item.job_fields))
