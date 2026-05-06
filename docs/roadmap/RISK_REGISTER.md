# Risk Register

| ID | Risk | Category | Impact | Likelihood | Severity | Mitigation | Related Tasks |
|---|---|---|---|---|---|---|---|
| RISK-001 | SQLite auth and billing data may be lost if mounted storage or backup handling is wrong | operational | High | Medium | critical | Document and validate backup/restore and durable storage assumptions | TASK-015 |
| RISK-002 | AI scoring calls can create cost spikes or provider outages | cost | High | High | critical | Document quotas, logging, and cost controls for scoring flows | TASK-011, TASK-013, TASK-018 |
| RISK-003 | Secrets could leak through environment handling, logs, or docs | security | High | Medium | critical | Inventory all env vars and document secret boundaries | TASK-011, TASK-012 |
| RISK-004 | Billing or auth regressions could block access or entitlement state | delivery | High | Medium | high | Document failure modes, smoke checks, and release gates | TASK-004, TASK-005, TASK-012 |
| RISK-005 | Test setup drift could make CI or local validation unreliable | maintainability | Medium | Medium | high | Document test layers, runtime versions, and regression workflow | TASK-008, TASK-009, TASK-010 |
| RISK-006 | Observability gaps could hide production failures until users report them | operational | High | High | high | Define logs, alerts, and monitoring expectations for critical endpoints | TASK-013, TASK-014 |
| RISK-007 | Deployment rollback could be unclear during a bad release | delivery | High | Medium | high | Document rollout and rollback steps tied to the current deploy path | TASK-004, TASK-005 |
| RISK-008 | The repo may accrete unsupported platform complexity if Kubernetes is added without need | maintainability | Medium | Medium | medium | Make an explicit deployment decision before adding cluster artifacts | TASK-016, TASK-017 |
| RISK-009 | Current docs are fragmented, so operators may miss important setup or recovery steps | maintainability | Medium | High | high | Add root-level onboarding and centralized operational docs | TASK-001, TASK-003, TASK-006 |
| RISK-010 | Performance and cost may degrade as AI usage grows | cost | High | Medium | high | Add cost and performance baselines before scaling usage | TASK-018, TASK-019 |
| RISK-011 | Public release could expose data or internal prompts without the right safeguards | security | High | Medium | critical | Tighten security documentation, logging constraints, and release gating | TASK-005, TASK-011, TASK-012, TASK-013 |
| RISK-012 | New feature work could start before the foundation is stable | technical | Medium | Medium | medium | Keep feature backlog downstream of production-readiness work | TASK-020 |
