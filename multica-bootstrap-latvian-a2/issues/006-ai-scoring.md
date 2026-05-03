[AI Scoring] Add rubric scoring, retries, quotas, and cost controls

Tasks:
1. Build provider abstraction for AI scoring.
2. Implement writing and speaking scoring rubrics with deterministic prompt templates.
3. Store prompt version, rubric version, model, input hash, provider status, score, feedback, retry/failure state, and estimated cost.
4. Add quotas by user/plan and retry caps.
5. Add request size limits and cost telemetry.
6. Clearly label scores as practice estimates, not official results.

Acceptance criteria:
- AI scoring only applies to writing/speaking/free text.
- Scoring output is schema validated.
- Retries and failure states are visible to user/admin.
- Quotas prevent unbounded LLM spend.
- Tests cover successful scoring, invalid model response, provider timeout, quota exceeded, and retry exhaustion.
