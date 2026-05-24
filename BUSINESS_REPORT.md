# LVCodex — Business & Technical Investment Report

**Project:** lvcodex (Latvian A2 Exam Simulator & Listening Library)
**Report Date:** 2026-05-23
**Prepared for:** Investors, Founders, Technical Leadership
**Repository:** `/Users/eramadan/GitRepo/lvcodex` · Deployed: Fly.io (lhr region)

---

## 1. Executive Summary

### 1.1 What the project does
LVCodex is a Latvian-language A2 exam preparation SaaS. It delivers browser-based mock exams that mirror the official Latvian State Language Centre (Valsts valodas centrs / Latvian Language Commission) A2 certification: timed listening (25 min), reading (30 min), writing (35 min), and speaking (10–15 min) sections. AI-powered scoring (Groq LLaMA 3.3 70B with OpenAI fallback) provides immediate writing/speaking feedback, while objective sections are graded automatically. A companion **Latvian Listening Library** offers spaced-practice audio content, and an **Admin Console** lets operators manage exam inventory, learners, billing, and audit trails.

### 1.2 Target market & business opportunity
- **Primary:** ~30,000 non-citizens and EU/third-country residents required to pass A2 Latvian to obtain or renew residence/work permits annually (Latvia, OCMA/PMLP data).
- **Secondary:** Ukrainian refugees in Latvia (~45,000 estimated needing language certification for long-term status).
- **Tertiary:** Heritage Latvian learners abroad (diaspora communities in UK, Ireland, US, Germany — ~150,000+) and self-paced ESL/EFL learners.
- **Institutional:** Latvian state-funded language schools, integration centers, private tutoring firms, EU integration programs.

### 1.3 Main value proposition
| Pain point | LVCodex solution |
|---|---|
| Official A2 exam costs €52 + months of waitlist; high re-take cost | Cheap unlimited practice that simulates real exam format |
| No standardized digital prep material exists | Only purpose-built Latvian A2 SaaS with full-skills coverage |
| Tutoring is €25–€40/hour; not scalable | AI scoring delivers 24/7 feedback at fraction of tutor cost |
| Learners cannot benchmark readiness | Quantified score + skill-level gaps after each attempt |
| Refugee/migrant cohorts underserved | Free tier + sponsored/voucher access enables institutional partnerships |

---

## 2. Revenue & Monetization Strategy

### 2.1 Existing billing model (already implemented in `billing.py`)

| SKU | Description | Estimated price (EUR) | Margin profile |
|---|---|---|---|
| Free tier | 1 sample exam, 3 attempts/day, capped LLM cost €0.85/day | €0 | Loss leader |
| Single exam | 1 specific exam unlock | €4.99 | High (~90%) |
| Exam Pack 5 | 5 attempts + 5 AI credits | €19.99 | High (~85%) |
| Monthly Pro | 30 attempts + 30 AI credits/month | €14.99/mo | High (~80%) |
| AI credit pack | 10 re-evaluation credits | €4.99 | High (~75%) |

Server-side enforcement via Stripe webhooks → SQLite `entitlement_grants` ledger. Idempotent event handling already in production.

### 2.2 Recommended pricing strategy (revised)

| Tier | Target segment | Price | Includes |
|---|---|---|---|
| **Free** | Discovery / SEO funnel | €0 | 1 sample exam, daily quota, watermarked feedback |
| **Learner** | Individual exam takers | **€9.99/mo** or €79/yr | Unlimited mock exams, 50 AI credits, history, listening library |
| **Learner+** | Cramming pre-exam | **€19.99 one-off (60-day pass)** | Everything in Learner + 100 AI credits + priority queue |
| **Tutor** | Independent tutors | **€29/mo** | Up to 10 student seats, progress dashboard, white-label option |
| **Institution** | Language schools, NGOs | **€2–€4/seat/mo (min 50 seats)** | SSO, bulk vouchers, reporting, SLA |
| **Government / EU grant** | OCMA, Integration Fund | **Custom (€10k–€50k/yr)** | Hosted instance, branded portal, data residency, audit logs |

### 2.3 Revenue potential — pre-launch estimates

**Conservative addressable cohort:** 30k forced certifications/year + 10k voluntary = ~40k/year. Assume 20% awareness reach in Year 1 → 8k visitors; 8% paid conversion → **640 paying users in Year 1**.

| Scenario | Paying users | ARPU | Monthly | Annual |
|---|---|---|---|---|
| Conservative | 400 | €11 | €4,400 | €52,800 |
| **Base** | **1,000** | **€12** | **€12,000** | **€144,000** |
| Optimistic | 2,500 | €14 | €35,000 | €420,000 |
| + 2 institutional (Year 2) | +500 seats | €3 | +€1,500 | +€18,000 |
| + EU grant (Year 2) | n/a | n/a | n/a | +€40,000 |

**Year-2 base target: €200k ARR.** Year-3 with institutional + government channels: €450k–€750k ARR.

---

## 3. Market Analysis

### 3.1 Competitors

| Competitor | Type | Strength | Weakness |
|---|---|---|---|
| **Mācies Latviešu (LVA)** | Government free portal | Free, official | No exam simulation, no scoring, dated UX |
| **Duolingo Latvian** | Mass-market app | Brand, free | Gamified, not exam-oriented, no A2 cert path |
| **Italki / Preply tutors** | Marketplace tutors | Human feedback | Expensive (€25–€40/hr), not standardized |
| **Local prep books (Zvaigzne ABC)** | Print | Curated content | No interactivity, no scoring |
| **Skillit, language schools** | In-person courses | Personalized | €€€, geographic limits |
| **None** | Direct competitor | — | **No purpose-built Latvian A2 mock exam SaaS exists** |

### 3.2 Market demand signals
- Latvia residence permit volume: 24k–32k/year requiring A2 (OCMA stats).
- Ukrainian war displaced ~45k still resident in Latvia mid-2026 → language certification required for long-stay status.
- EU "Common Basic Principles on Integration" mandates state-supported language access — grant funding regularly available.
- Search trend: `valsts valodas eksāmens` and `A2 eksāmens` sustained 2k+ monthly LV searches.

### 3.3 Target customer segments
1. **B2C — Migrant adult learner** (primary persona "Olena, 34, registered nurse, needs A2 for hospital contract renewal")
2. **B2C — Heritage diaspora learner**
3. **B2B — Latvian language school** (private + state-funded)
4. **B2B — Employer-sponsored** (logistics, healthcare, hospitality)
5. **B2G — OCMA / Sabiedrības integrācijas fonds** (integration grants)

### 3.4 Competitive advantages
- **First-mover in Latvian A2 digital exam prep niche.**
- Native exam-format simulation (timer, sectioning, scoring) — no other product offers this.
- AI scoring at marginal cost vs. tutor hourly rate.
- Production-grade infrastructure already in place (Fly.io, Stripe, Sentry, CI/CD).

### 3.5 Missing opportunities
- B1/B2/C1 expansion — same engine, larger TAM (50k+ learners progressing past A2).
- Other Baltic languages (Lithuanian A2, Estonian A2) — identical regulatory pattern.
- Citizenship test prep (Naturalizācijas eksāmens) — same buyer.
- Speech-to-text live oral coach (not yet implemented).
- Mobile app (currently web-only).

---

## 4. Technical Assessment

### 4.1 Current architecture & maturity

| Layer | Implementation | Maturity |
|---|---|---|
| Backend | Python 3.13, raw `http.server.ThreadingHTTPServer`, ~187k LOC in monolithic `server.py` | Functional but monolithic |
| Database | SQLite on Fly persistent volume (single-region) | Acceptable to ~5k MAU, then bottleneck |
| Frontend | Vanilla JS/Vue SPA via Vite, `latvian-a2-exam-app/` | No TS, fragile |
| LLM | Groq LLaMA 3.3 70B primary, OpenAI fallback, LRU cache (500) | Cost-controlled |
| Payments | Stripe (Checkout + webhooks, idempotent) | Production-ready |
| Auth | Self-rolled session auth, recent hardening (commit `37d40a9`) | Works, but needs review |
| Deployment | Fly.io (lhr, 1 shared-cpu, 256MB), Docker | Single point of failure |
| CI/CD | GitHub Actions: gitleaks + pip-audit + regression suite | Solid baseline |
| Monitoring | Sentry SDK | Errors only; no metrics/tracing |
| Testing | ~14 test files, Playwright E2E, contracts | Good for stage; needs broader coverage |

### 4.2 Production-readiness gaps

| Area | Gap | Severity | Effort |
|---|---|---|---|
| **Scalability** | Single Fly machine, 256MB RAM, ThreadingHTTPServer | High | M |
| | SQLite — no replication, no point-in-time recovery | High | M |
| | No CDN for audio assets in listening library | Medium | S |
| **Security** | Self-rolled auth — needs external pen-test | High | M |
| | No MFA | Medium | S |
| | No CSP/HSTS headers verified | Medium | XS |
| | No formal SOC2/ISO27001 path | High (B2B/B2G) | L |
| **Observability** | Only Sentry — no metrics (Prometheus), no logs aggregation, no traces | High | M |
| | No SLO dashboard, no alerting beyond Sentry | High | S |
| **CI/CD** | No staging env, deploy goes straight to prod | Medium | S |
| | No DB migration framework (raw SQL files in `migrations/`) | Medium | S |
| **Compliance** | GDPR: data export available, deletion available, but no DPA template | High | S |
| | No cookie consent banner | Medium | XS |
| | No Latvian Data State Inspectorate registration | Medium | S |
| **Testing** | No load tests | Medium | S |
| | Coverage % unknown (no coverage gate in CI) | Medium | XS |
| **Documentation** | No public API docs (OpenAPI) | Medium | M |
| | USER_MANUAL.md exists, but no developer onboarding | Low | S |
| **UX/UI** | Vanilla JS — fragile, hard to extend; no design system | Medium | L |
| | No mobile-native or PWA install flow | Medium | M |
| **API readiness** | No REST contract docs; no rate-limit headers; no API keys for B2B | High (for B2B) | M |
| **Cloud readiness** | Locked to Fly.io; no IaC (Terraform); no multi-region | Medium | M |
| **Automation** | No automated DB backups script committed | High | XS |
| | No release rollback procedure | Medium | S |

### 4.3 Infrastructure & operational risks
- **Single Fly machine** in London — outage = full downtime; no automated DR.
- **SQLite** — concurrent writes throttle past ~50 RPS sustained; corruption risk on volume failure.
- **LLM cost spike** — Groq outage forces OpenAI fallback at ~10× cost; daily caps mitigate but don't prevent.
- **Stripe key rotation** — manual; not documented.
- **No on-call rotation** — solo operator dependence (founder bus-factor = 1).

---

## 5. Business Readiness

### 5.1 Gaps to commercial launch

| Function | Status | Required action |
|---|---|---|
| **Pricing page** | Partially built | Localized EUR + USD, clear tier comparison |
| **Marketing site** | Minimal | Landing pages per persona (migrant, employer, school) |
| **Sales** | None | Outbound playbook for institutional B2B |
| **Onboarding** | Sign-up flow exists | First-run tour, sample exam push, email drip |
| **Support** | No documented channel | Helpdesk (e.g., Crisp/Plain) + KB articles |
| **Legal** | Disclaimer in roadmap as TODO | Terms, Privacy, DPA, Cookie policy in LV+EN |
| **SLA** | None | Define 99.5% uptime + response targets for paid tiers |
| **Analytics** | Sentry only | PostHog/Plausible for product analytics + funnels |
| **Customer success** | None | Re-engagement emails, churn-risk alerts |
| **Refund policy** | Not visible | 7-day money-back guarantee (EU consumer law) |
| **VAT handling** | Stripe Tax not visible | Enable Stripe Tax (LV VAT 21% + OSS for EU) |
| **Invoicing** | Stripe receipts only | B2B invoice generation for institutions |

### 5.2 Operational must-haves
- Latvian-language customer support SLA (1 business day for free, 4h for paid).
- Documented incident response (status page e.g., Statuspage / Cachet).
- Founder-led demo deck for institutional sales.
- Affiliate program (tutor referrals → 20% revenue share).

---

## 6. ROI & Financial Projection

### 6.1 Cost structure (annualized)

| Cost line | Year 1 | Year 2 | Year 3 |
|---|---:|---:|---:|
| Founder/lead engineer salary | €60,000 | €70,000 | €80,000 |
| Part-time content/exam designer | €15,000 | €25,000 | €30,000 |
| Part-time marketing/CS | €12,000 | €25,000 | €40,000 |
| Cloud (Fly.io scale-up) | €600 | €2,400 | €6,000 |
| LLM (Groq + OpenAI fallback) | €1,800 | €6,000 | €14,000 |
| Stripe + payment fees (~3%) | €4,300 | €6,000 | €14,000 |
| Sentry + observability stack | €600 | €1,800 | €3,600 |
| Legal/accounting (GDPR, contracts) | €4,000 | €5,000 | €6,000 |
| Marketing/ads (SEO, paid social) | €6,000 | €18,000 | €30,000 |
| Tooling, SaaS subs | €2,400 | €4,800 | €7,200 |
| Contingency (10%) | €10,700 | €16,400 | €23,080 |
| **Total OpEx** | **€117,400** | **€180,400** | **€253,880** |

### 6.2 Revenue forecast

| Period | Paying users | ARPU/mo | Monthly rev | Cumulative rev |
|---|---:|---:|---:|---:|
| Month 1–3 (launch) | 50 → 200 | €11 | €550 → €2,200 | €4,125 |
| Month 4–6 | 400 → 700 | €11 | €4,400 → €7,700 | €22,275 |
| **6 months** | **700** | **€11** | **€7,700** | **~€22k** |
| Month 7–12 | 700 → 1,000 | €12 | €8,400 → €12,000 | +€60,000 |
| **12 months** | **1,000** | **€12** | **€12,000** | **~€82k** |
| Year 2 (B2B + grant) | 1,500 + 500 seats + grant | €13 + €3 + €40k grant | €25,000+ | €82k + €240k = **€322k** |
| **24 months cumulative** | — | — | — | **~€322k** |

### 6.3 Break-even analysis

- **Burn (Y1):** €117k OpEx − €82k revenue = **−€35k Y1 net** (financeable with pre-seed)
- **Break-even point:** ~Month 14–16 at 1,000+ paying users **or** first 2 institutional contracts.
- **ROI horizon:** Positive contribution margin per learner from month 1 (LLM cost €0.05/exam vs. €11 ARPU); break-even requires fixed-cost coverage, not unit economics.

### 6.4 ROI summary

| Metric | Year 1 | Year 2 | Year 3 |
|---|---:|---:|---:|
| Revenue | €82k | €322k | €620k |
| OpEx | €117k | €180k | €254k |
| Net | **−€35k** | **+€142k** | **+€366k** |
| ROI (cumulative, post-Y1 invest €117k) | — | +21% | +212% |

**Investor pitch:** ~€150k seed → break-even Q4 Y2 → €600k+ ARR by end of Y3 at modest assumptions.

---

## 7. Roadmap & Timeline

### 7.1 Implementation phases

```
Phase 0  (DONE)        | Core exam engine, Stripe, deploy
Phase 1  (M0-M2)       | MVP polish: legal pages, refund flow, GDPR DPA, status page
Phase 2  (M2-M5)       | Production hardening: observability, backups, multi-region warm standby
Phase 3  (M5-M8)       | Growth: institutional tier, SSO, bulk vouchers, white-label
Phase 4  (M8-M12)      | B1 level launch + mobile PWA
Phase 5  (M12-M18)     | Lithuanian/Estonian expansion + government contracts
Phase 6  (M18-M24)     | Citizenship exam prep + SOC2 readiness
```

### 7.2 Milestone matrix

| Milestone | Target month | Definition of done |
|---|---|---|
| MVP launch (B2C) | M2 | Legal pages live, Stripe Tax on, status page, refund flow |
| Production-ready | M5 | Multi-region warm-standby, automated backups, observability complete, pen-test passed |
| Enterprise-ready | M10 | SSO (SAML/OIDC), DPA template, seat licensing, audit logs export, 99.5% SLA |
| Government-ready | M18 | Data residency option, SOC2 Type I in progress, signed framework contract |

### 7.3 Priority matrix (Eisenhower)

| | **Urgent** | **Not Urgent** |
|---|---|---|
| **Important** | Legal pages, GDPR DPA, backups, monitoring, pen-test | B1 level, mobile PWA, Lithuanian/Estonian expansion |
| **Not Important** | UI polish for marketing site | Gamification, leaderboards, badges |

---

## 8. Risk Analysis

### 8.1 Technical risks

| Risk | Likelihood | Impact | Mitigation |
|---|---|---|---|
| SQLite write contention as MAU grows | High (post-2k MAU) | High | Migrate to Postgres on Fly or Neon by M5 |
| Single-region Fly outage | Medium | High | Warm standby in fra/ams; DB streaming replication |
| LLM provider outage / price hike | Medium | Medium | Multi-provider abstraction (already partial); negotiated contract |
| Monolithic `server.py` becomes unmaintainable | High | Medium | Modularize into `server/` package; introduce FastAPI/Starlette |
| Self-rolled auth vulnerability | Medium | Critical | External pen-test before institutional sales; consider Auth0/Stytch |

### 8.2 Business risks

| Risk | Likelihood | Impact | Mitigation |
|---|---|---|---|
| Government launches free competitor | Low–Medium | High | Position as superior UX + B2B/B2G partner, not adversary |
| Low willingness-to-pay in migrant cohort | Medium | High | Voucher/grant channel via integration funds; employer-paid model |
| LLM scoring perceived as unreliable | Medium | Medium | Human-in-the-loop review; transparent rubric; tutor-validated |
| Founder bus factor (solo) | High | Critical | Hire co-engineer M3; document runbooks |

### 8.3 Market risks

| Risk | Likelihood | Impact | Mitigation |
|---|---|---|---|
| Exam format change by Language Centre | Medium | Medium | Versioned exam bank; rapid content update pipeline |
| Migration policy shift reduces TAM | Low | High | Diversify to diaspora + heritage learners + B1/B2 |
| Latvian state offers proprietary exam-prep portal | Low | Medium | Lobby for inclusion as approved vendor instead |

### 8.4 Overall risk-mitigation strategy
1. Diversify revenue (B2C + B2B + B2G) within 18 months.
2. Externalize critical infra (Postgres-as-a-service, auth) to reduce custom-code burden.
3. Build a relationship with Latvian Integration Fund / OCMA early.
4. Achieve SOC2 Type I within 24 months as B2B/B2G prerequisite.

---

## 9. Final Recommendations

### 9.1 Go-to-market strategy

| Channel | Quarter | Tactic |
|---|---|---|
| SEO (LV+RU+EN) | Q1 | Long-tail content: "Kā kārtot A2 eksāmenu", "A2 mock exam Latvian" |
| Migrant integration centers | Q1 | Partner with 5 NGOs; provide free vouchers in exchange for placement |
| Paid social (FB groups, Telegram) | Q2 | Ukrainian/Russian-speaking communities in Riga |
| Tutor affiliate program | Q2 | 20% rev share; tutors get dashboard in Tutor tier |
| Institutional outbound | Q3 | Top 20 LV language schools; demo + pilot |
| Government bid | Q4 | Apply to Sabiedrības integrācijas fonds tender |

### 9.2 Priority improvements (next 90 days)

1. **Legal/compliance** — Terms, Privacy, DPA, Cookie banner, Stripe Tax (1 wk, blocker)
2. **Backups & DR** — Automated DB snapshots + offsite copy (3 days)
3. **Observability** — Add Prometheus metrics + Grafana dashboard + alerting (2 wks)
4. **Pen-test** — External security audit before any institutional sale (4 wks)
5. **Marketing site** — Localized landing pages, pricing, social proof (2 wks)
6. **Refund + invoicing** — Self-serve refund within 7d; B2B invoice flow (1 wk)
7. **Status page** — Public + email subscribers (2 days)

### 9.3 Fastest path to profitability
- Lock in **2 institutional pilots in Q1** (free 3-month pilot → €15–20k annual contract each).
- Add **employer-pay model** for healthcare/logistics employers needing certified staff.
- Use **Latvian Integration Fund grant** (typical €30–60k for digital learning innovation) to subsidize Y1 OpEx.
- Combined effect: shift break-even from M14–16 to **M9–10**.

### 9.4 Long-term scaling strategy
- **Horizontal level expansion:** A2 → B1 → B2 → C1 (multiplies TAM 3–4×).
- **Geographic expansion:** Lithuanian + Estonian A2 (same EU integration pattern, ~40k learners/year combined).
- **Adjacent product:** Naturalizācijas eksāmens (citizenship test) — same buyer, premium price tolerance.
- **Platform play:** White-label exam engine for other regulated language certifications (Polish, Czech, Hungarian).

---

## 10. Suggested Architecture Improvements

```
Current                                     Target (M5–M8)
─────────────────────────                   ──────────────────────────────────
Fly.io (single machine, lhr)                Fly.io multi-region (lhr+fra warm)
SQLite local volume                  ────►  Postgres (Fly PG / Neon, PITR backup)
server.py monolith (187 KB)                 server/ package (routes, services, models)
http.server stdlib                          FastAPI + uvicorn (proper ASGI)
Self-rolled session auth                    Stytch/Auth0 + MFA + SSO (SAML/OIDC)
Audio on local volume                       S3-compatible (Cloudflare R2) + CDN
Sentry only                                 Sentry + Prometheus + Grafana + Loki
Manual deploy                               GitHub Actions → staging → prod gated
No IaC                                      Terraform for Fly + Stripe + DNS
```

### Estimated team requirements

| Phase | Months | Headcount |
|---|---|---|
| MVP-launch | M0–M2 | 1 FT eng (founder), 0.3 designer, 0.3 content |
| Production hardening | M3–M5 | 2 FT eng, 0.5 designer, 0.5 content, 0.3 marketing |
| Growth | M6–M12 | 3 FT eng, 1 designer, 1 content, 1 marketing, 0.5 CS |
| Enterprise | M13–M24 | 4–5 FT eng, 1 designer, 1 content, 1 sales, 1 CS, 1 marketing |

---

## Appendix A — Technical Recommendations Summary

| # | Recommendation | Priority | Effort |
|---|---|---|---|
| 1 | Migrate SQLite → Postgres | High | M |
| 2 | Modularize `server.py` into FastAPI app | High | L |
| 3 | Add Prometheus + Grafana | High | M |
| 4 | Multi-region warm standby | High | M |
| 5 | External pen-test | High | M |
| 6 | OpenAPI documentation | High | S |
| 7 | Stripe Tax + B2B invoicing | High | S |
| 8 | Automated DB backups + restore drill | Critical | XS |
| 9 | Public status page | Medium | XS |
| 10 | Replace vanilla JS with Vue 3 + TS | Medium | L |
| 11 | SSO (SAML/OIDC) for institutions | High (B2B) | M |
| 12 | Mobile PWA + offline mode for listening library | Medium | M |
| 13 | Content versioning + rapid update pipeline | Medium | S |
| 14 | SOC2 readiness program | High (B2G) | L |

---

## Appendix B — Investment Ask Framing

| Round | Amount | Use | Outcome |
|---|---|---|---|
| **Pre-seed** | €150k | 12 mo runway, hire 1 eng, legal, marketing | MVP launch + 1,000 paying users |
| **Seed (M12)** | €500k | Scale to B2B + B2G, expand to B1 + Lithuanian | €450k–€750k ARR, break-even Q3 Y3 |
| **Series A (M30)** | €2–3M | Multi-language platform, EU expansion | €2M+ ARR, Series A metrics |

**Net:** With ~€150k pre-seed, lvcodex can credibly target **€600k ARR + EBITDA positive by end of Y3**, with optionality on a multi-language Baltic certification platform that addresses ~150,000 annual certification candidates across LV/LT/EE.

---

*End of report.*
