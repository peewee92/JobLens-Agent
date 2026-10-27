from pydantic import Field

from app.api.v1.schemas.common import CamelCaseModel
from app.application.system_readiness import CheckStatus, ReadinessCode, SystemReadiness


class ReadinessChecks(CamelCaseModel):
    database: CheckStatus
    migrations: CheckStatus
    tables: CheckStatus


class SystemReadinessResponse(CamelCaseModel):
    ready: bool
    code: ReadinessCode
    checks: ReadinessChecks
    current_revisions: list[str] = Field(default_factory=list)
    required_revisions: list[str] = Field(default_factory=list)
    missing_tables: list[str] = Field(default_factory=list)

    @classmethod
    def from_result(cls, result: SystemReadiness) -> "SystemReadinessResponse":
        return cls(
            ready=result.ready, code=result.code,
            checks=ReadinessChecks(database=result.database, migrations=result.migrations, tables=result.tables),
            current_revisions=list(result.current_revisions),
            required_revisions=list(result.required_revisions),
            missing_tables=list(result.missing_tables),
        )
