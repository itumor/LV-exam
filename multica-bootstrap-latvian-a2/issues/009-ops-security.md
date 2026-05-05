[Ops] Deploy with HTTPS, monitoring, backups, rate limits, and legal pages

Tasks:
1. Prepare production deployment with HTTPS and custom domain.
2. Store secrets in platform-managed environment variables.
3. Add structured logs and Sentry monitoring.
4. Alert on API errors, scoring failures, payment webhook failures, login failures, and high LLM cost.
5. Configure database backups.
6. Add admin-only access controls, rate limiting, and abuse protection.
7. Add privacy policy, terms of service, and clear unofficial simulator disclaimer.

Acceptance criteria:
- Deployment docs exist with env var matrix.
- Health checks and monitoring are configured.
- Backups are documented and tested.
- Legal pages and disclaimer are visible before payment and on results.
- Security review documents key risks and mitigations.
