"""Repeatable Profile Extraction evaluation runner."""
from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

from app.workflows import ProposeProfileFromResumeWorkflow


@dataclass(frozen=True, slots=True)
class ProfileEvalCase:
    id: str
    resume_text: str
    expected_skills: tuple[str, ...]
    expected_years: float | None
    forbidden_terms: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class ProfileEvalFailure:
    case_id: str
    reason: str


@dataclass(frozen=True, slots=True)
class ProfileEvalReport:
    total: int
    passed: int
    failures: tuple[ProfileEvalFailure, ...]

    @property
    def pass_rate(self) -> float:
        return self.passed / self.total if self.total else 0.0


def load_profile_eval_cases(path: Path) -> tuple[ProfileEvalCase, ...]:
    cases = []
    for line_number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        if not line.strip():
            continue
        data = json.loads(line)
        cases.append(
            ProfileEvalCase(
                id=str(data["id"]),
                resume_text=str(data["resumeText"]),
                expected_skills=tuple(str(item) for item in data["expectedSkills"]),
                expected_years=(
                    float(data["expectedYears"])
                    if data.get("expectedYears") is not None
                    else None
                ),
                forbidden_terms=tuple(
                    str(item) for item in data.get("forbiddenTerms", [])
                ),
            )
        )
    if not cases:
        raise ValueError(f"No Profile Eval cases found in {path}")
    return tuple(cases)


def run_profile_eval(
    workflow: ProposeProfileFromResumeWorkflow,
    cases: tuple[ProfileEvalCase, ...],
) -> ProfileEvalReport:
    failures: list[ProfileEvalFailure] = []
    for case in cases:
        try:
            output = workflow.execute(case.resume_text)
        except Exception as error:
            failures.append(
                ProfileEvalFailure(case.id, f"extract/validate failed: {error}")
            )
            continue

        output_skills = {item.name.casefold() for item in output.skills}
        missing_skills = [
            skill for skill in case.expected_skills if skill.casefold() not in output_skills
        ]
        if missing_skills:
            failures.append(
                ProfileEvalFailure(
                    case.id,
                    f"missing expected skill: {missing_skills[0]}",
                )
            )
            continue

        if case.expected_years is not None:
            if output.years_of_experience is None or abs(
                output.years_of_experience - case.expected_years
            ) > 0.5:
                failures.append(
                    ProfileEvalFailure(
                        case.id,
                        "yearsOfExperience outside 0.5-year tolerance",
                    )
                )
                continue

        serialized = json.dumps(
            {
                "headline": output.headline,
                "evidence": [item.summary for item in output.evidence],
                "skills": [item.name for item in output.skills],
            },
            ensure_ascii=False,
        ).casefold()
        forbidden = next(
            (
                term
                for term in case.forbidden_terms
                if term.casefold() in serialized
            ),
            None,
        )
        if forbidden:
            failures.append(
                ProfileEvalFailure(
                    case.id,
                    f"forbidden unsupported fact appeared: {forbidden}",
                )
            )

    return ProfileEvalReport(
        total=len(cases),
        passed=len(cases) - len(failures),
        failures=tuple(failures),
    )
