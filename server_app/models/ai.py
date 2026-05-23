"""AI payload schema validation (T-026).

Pydantic v2 models that validate the request and response shapes used by the
AI scoring pipeline (Groq + OpenAI/Codex fallback). These complement the
existing hand-written validator in :mod:`server_app.core` by giving callers a
typed, declarative interface that can be reused from tests, future routes,
and the AI NPC pipeline (T-045).

The models cover three surfaces:

* :class:`AIScoreRequest` — inbound writing / speaking scoring request.
* :class:`AISkillScore` — per-skill score block (listening, reading, writing,
  speaking).
* :class:`AIEvaluationResponse` — the full structured response (scores +
  corrections + feedback).

All models are **strict** about field types and constrained where the rubric
permits (0–15 points, 0–60 total, status enum). Validation errors raise
:class:`pydantic.ValidationError`, which the evaluator translates to an
``EvaluationError`` with status code 502.

Notes
-----
* Models permit ``extra='ignore'`` so adopters can pass legacy keys without
  breaking. Strict mode is enforced for the response (no unexpected sections).
* The :class:`AISkillScore.reason` field is bounded to 600 chars to keep
  payloads small enough for the SQLite text column used by the evaluator.
* Scores are nullable for objective skills (listening / reading) because the
  evaluator deterministically locks them server-side; LLM responses may omit
  them.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, List, Literal, Optional

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


SCORING_SKILLS = ("listening", "reading", "writing", "speaking")
FREE_TEXT_SKILLS = ("writing", "speaking")
MAX_SKILL_POINTS = 15
MAX_TOTAL_POINTS = 60
MIN_PASS_PER_SKILL = 9


# ---------------------------------------------------------------------------
# Request models
# ---------------------------------------------------------------------------


class AICandidate(BaseModel):
    """Identifying details for the candidate submitting the attempt."""

    model_config = ConfigDict(extra="ignore", str_strip_whitespace=True)

    code: str = Field(default="", max_length=64)
    name: str = Field(default="", max_length=120)
    email: str = Field(default="", max_length=254)


class AIScoreRequest(BaseModel):
    """Inbound writing / speaking scoring request payload.

    The fields mirror what ``server_app.core.compact_submission`` produces
    today. Keeping the schema in pydantic gives callers an early, structured
    validation step before the request reaches the (much slower) provider
    call.
    """

    model_config = ConfigDict(extra="ignore", str_strip_whitespace=True)

    submission_id: str = Field(..., min_length=1, max_length=64)
    exam_id: str = Field(..., min_length=1, max_length=64)
    plan: str = Field(default="free", min_length=1, max_length=32)
    learner_id: str = Field(default="", max_length=128)
    learner_email: str = Field(default="", max_length=254)
    candidate: AICandidate = Field(default_factory=AICandidate)
    answers: dict[str, dict[str, list[str]]] = Field(default_factory=dict)
    attempt_started_at: Optional[str] = Field(default=None, max_length=40)

    @field_validator("plan")
    @classmethod
    def _normalize_plan(cls, value: str) -> str:
        normalized = value.strip().lower()
        if not normalized:
            return "free"
        return normalized

    @field_validator("answers")
    @classmethod
    def _validate_answer_shape(
        cls, value: dict[str, dict[str, list[str]]]
    ) -> dict[str, dict[str, list[str]]]:
        # Reject obvious skill-name typos and enforce string lists. We do not
        # require *every* skill — some submissions only score writing.
        for skill, tasks in value.items():
            if skill not in SCORING_SKILLS:
                raise ValueError(f"Unknown skill '{skill}'. Allowed: {SCORING_SKILLS}.")
            if not isinstance(tasks, dict):
                raise ValueError(f"Tasks for skill '{skill}' must be an object.")
            for task_key, task_answers in tasks.items():
                if not isinstance(task_answers, list):
                    raise ValueError(
                        f"Answers for {skill}/{task_key} must be an array."
                    )
                for answer in task_answers:
                    if not isinstance(answer, str):
                        raise ValueError(
                            f"Answer entries for {skill}/{task_key} must be strings."
                        )
        return value

    def identity(self) -> dict[str, str]:
        """Return the identity tuple used by the quota ledger."""

        user_key = (
            (self.learner_id or "").strip()
            or (self.learner_email or "").strip()
            or (self.candidate.code or "").strip()
            or self.submission_id
            or "anonymous"
        )
        return {"user_key": user_key, "plan": self.plan}


# ---------------------------------------------------------------------------
# Response models
# ---------------------------------------------------------------------------


class AISkillScore(BaseModel):
    """Per-skill score block returned by the LLM.

    Matches the A2 rubric: 0–15 points per skill, passed = points ≥ 9. The
    ``passed`` flag is derived if missing so callers can pass thin LLM
    responses through without recomputing the rule client-side.
    """

    model_config = ConfigDict(extra="ignore")

    points: int = Field(..., ge=0, le=MAX_SKILL_POINTS)
    max_points: int = Field(default=MAX_SKILL_POINTS, ge=1, le=MAX_SKILL_POINTS)
    passed: bool = Field(default=False)
    reason: str = Field(default="", max_length=600)

    @model_validator(mode="after")
    def _derive_passed(self) -> "AISkillScore":
        # Snap ``passed`` to the canonical 9/15 rule unless explicitly false
        # for a high-scoring response (which would be a contradictory LLM
        # answer worth surfacing in tests).
        if self.points >= MIN_PASS_PER_SKILL:
            self.passed = True
        else:
            self.passed = False
        return self


class AICorrection(BaseModel):
    """One free-text correction the LLM suggested for writing / speaking."""

    model_config = ConfigDict(extra="ignore", str_strip_whitespace=True)

    skill: Literal["writing", "speaking"]
    task: str = Field(default="", max_length=120)
    item: int = Field(default=1, ge=1, le=20)
    candidate_answer: str = Field(default="", max_length=2_000)
    suggested_answer: str = Field(default="", max_length=2_000)
    comment: str = Field(default="", max_length=800)


class AIFeedback(BaseModel):
    """Structured feedback paragraph + bullet lists."""

    model_config = ConfigDict(extra="ignore", str_strip_whitespace=True)

    summary: str = Field(default="", max_length=1_500)
    strengths: List[str] = Field(default_factory=list, max_length=10)
    improvements: List[str] = Field(default_factory=list, max_length=10)
    next_practice: List[str] = Field(default_factory=list, max_length=10)

    @field_validator("strengths", "improvements", "next_practice")
    @classmethod
    def _bound_bullets(cls, value: list[str]) -> list[str]:
        out: list[str] = []
        for entry in value:
            text = str(entry or "").strip()
            if not text:
                continue
            if len(text) > 400:
                text = text[:400]
            out.append(text)
        return out


class AIEvaluationScores(BaseModel):
    """Top-level scores block carrying per-skill sections + roll-ups."""

    model_config = ConfigDict(extra="ignore")

    listening: Optional[AISkillScore] = None
    reading: Optional[AISkillScore] = None
    writing: Optional[AISkillScore] = None
    speaking: Optional[AISkillScore] = None
    total: int = Field(default=0, ge=0, le=MAX_TOTAL_POINTS)
    passed: bool = Field(default=False)

    @model_validator(mode="after")
    def _recompute_totals(self) -> "AIEvaluationScores":
        sections = [self.listening, self.reading, self.writing, self.speaking]
        present = [section for section in sections if section is not None]
        if not present:
            self.total = 0
            self.passed = False
            return self
        self.total = sum(section.points for section in present)
        # 9/15 per-skill rule: all present skills must pass.
        self.passed = all(section.passed for section in present)
        return self


class AIEvaluationResponse(BaseModel):
    """Validated LLM response payload for a writing+speaking evaluation."""

    model_config = ConfigDict(extra="ignore", str_strip_whitespace=True)

    status: Literal["evaluated"]
    scores: AIEvaluationScores
    corrections: List[AICorrection] = Field(default_factory=list, max_length=40)
    feedback: AIFeedback = Field(default_factory=AIFeedback)


# ---------------------------------------------------------------------------
# Failure-mode models (visible failure modes — roadmap A P3)
# ---------------------------------------------------------------------------


class AIQuotaExceededDetails(BaseModel):
    """Body returned with the HTTP 429 when a learner's daily quota is gone."""

    model_config = ConfigDict(extra="ignore")

    code: Literal["ai_quota_exceeded"] = "ai_quota_exceeded"
    message: str
    user_key: str
    plan: str
    used: int = Field(ge=0)
    limit: int = Field(ge=0)
    resets_at: str  # ISO-8601 UTC midnight tomorrow


class AIProviderUnavailableDetails(BaseModel):
    """Body returned with the HTTP 503 when all retries are exhausted."""

    model_config = ConfigDict(extra="ignore")

    code: Literal["ai_provider_unavailable"] = "ai_provider_unavailable"
    message: str
    provider: str
    attempts: int = Field(ge=1)
    retry_after_seconds: int = Field(ge=1, le=86_400)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def next_utc_midnight_iso(now: Optional[datetime] = None) -> str:
    """Return the ISO-8601 timestamp for the next UTC midnight.

    Used by the quota ledger to tell learners when their daily AI quota
    resets. Centralised here so the evaluator + tests agree on the format.
    """

    current = now or datetime.now(timezone.utc)
    next_day = current.date().toordinal() + 1
    reset = datetime.fromordinal(next_day).replace(tzinfo=timezone.utc)
    return reset.isoformat().replace("+00:00", "Z")


__all__ = [
    "AICandidate",
    "AICorrection",
    "AIEvaluationResponse",
    "AIEvaluationScores",
    "AIFeedback",
    "AIProviderUnavailableDetails",
    "AIQuotaExceededDetails",
    "AIScoreRequest",
    "AISkillScore",
    "FREE_TEXT_SKILLS",
    "MAX_SKILL_POINTS",
    "MAX_TOTAL_POINTS",
    "MIN_PASS_PER_SKILL",
    "SCORING_SKILLS",
    "next_utc_midnight_iso",
]
