# Latvian A2 Exam Platform — 2-Year Copy-Paste Product Roadmap

**Products covered**

- A2 Exam Practice App: `https://latvian-a2-exam.fly.dev/latvian-a2-exam-app/`
- Listening Library: `https://latvian-a2-exam.fly.dev/latvian-listening-library/`

**Primary goal**

Build a highly engaging, ethical, exam-focused Latvian A2 learning platform that helps learners pass the Latvian state language A2 exam by training all four required skills: **listening, reading, writing, and speaking**.

**Exam baseline from uploaded official A2 material**

- Total score: **60 points**
- Four skills: **Listening, Reading, Writing, Speaking**
- Each skill: **15 points**
- Minimum passing requirement: **9/15 per skill**
- Listening duration: **25 min**
- Reading duration: **30 min**
- Writing duration: **35 min**
- Speaking duration: **10-15 min**
- Product rule: **A learner is not "exam ready" unless all four predicted skill scores are at least 9/15.**

---

## 1. Roadmap operating model

### 1.1 Roadmap structure

Use this roadmap as GitHub Issues, Jira Epics, Linear tasks, or GitLab Issues.

Each item has:

```text
Epic
├── Tasks
│   ├── Subtasks
│   ├── Validation / Acceptance Criteria
│   ├── E2E Tests
│   ├── Analytics Events
│   └── Definition of Done
```

### 1.2 Priority levels

| Priority | Meaning |
|---|---|
| P0 | Required for A2 exam-prep credibility |
| P1 | Important for retention, learning quality, or monetization |
| P2 | Strong improvement, not required for first stable release |
| P3 | Advanced / scale / future differentiation |

### 1.3 Global Definition of Done

A task is complete only when all are true:

- [ ] Feature works on desktop and mobile viewport.
- [ ] Feature has empty, loading, error, and success states.
- [ ] Feature has accessibility labels where needed.
- [ ] Feature stores correct data in the database.
- [ ] Feature emits analytics events.
- [ ] Feature has unit/integration tests where applicable.
- [ ] Feature has at least one E2E test for the main user path.
- [ ] Feature has no learner-facing admin/debug leakage.
- [ ] Feature does not use dark patterns or shame-based retention.
- [ ] Feature supports the A2 exam pass logic: **minimum 9/15 per skill**.

---

## 2. Target product architecture

```text
Latvian A2 Exam Platform
│
├── Learner App
│   ├── Home / Daily Mission
│   ├── A2 Readiness Dashboard
│   ├── Exam Simulator
│   ├── Listening Library
│   ├── Reading Practice
│   ├── Writing Coach
│   ├── Speaking Coach
│   ├── Vocabulary / SRS
│   └── Progress Map
│
├── Admin / CMS
│   ├── Exam Schema
│   ├── Audio Content
│   ├── Reading Texts
│   ├── Writing Prompts
│   ├── Speaking Prompts
│   ├── Question Bank
│   ├── Mock Exams
│   └── Content QA
│
├── Learning Engine
│   ├── Skill Score Prediction
│   ├── Weak-Skill Detection
│   ├── Daily Mission Generator
│   ├── Spaced Repetition
│   ├── XP / Streaks / Badges
│   └── Personalization Rules
│
├── Analytics
│   ├── Retention
│   ├── Skill Progress
│   ├── Mistake Patterns
│   ├── Feature Engagement
│   ├── Exam Readiness
│   └── Revenue
│
└── Infrastructure
    ├── Auth
    ├── PostgreSQL
    ├── Object Storage for Audio / Images
    ├── Background Jobs
    ├── Error Tracking
    ├── Observability
    └── CI/CD
```

---

## 3. Product north star

### 3.1 North Star Metric

```text
Number of active learners predicted to score >= 9/15 in all four A2 skills.
```

### 3.2 Supporting metrics

| Metric | Target use |
|---|---|
| D1 retention | Validate onboarding |
| D7 retention | Validate habit loop |
| D30 retention | Validate long-term value |
| Daily mission completion | Validate engagement |
| Weak-skill repair completion | Validate learning recovery |
| Mock exam completion | Validate exam seriousness |
| Lowest predicted skill score | Validate true readiness |
| Writing resubmission rate | Validate feedback usefulness |
| Speaking recording completion | Validate productive-skill adoption |
| Audio load error rate | Validate platform reliability |

---

# YEAR 1 — Build a credible A2 exam-prep platform

## Quarter 1 — Foundation, stability, and exam alignment

**Theme:** Make the existing apps reliable, connected, measurable, and officially aligned.

**Outcome by end of Q1:** A learner can log in, complete listening practice, see skill readiness, and receive one daily mission based on exam structure.

---

## Epic Q1.1 — Unified A2 exam schema

**Priority:** P0
**Goal:** Create a single source of truth for skills, task types, scoring, timing, and pass rules.

### Tasks

- [ ] Create `exam_levels` table/entity.
- [ ] Create `skills` table/entity: listening, reading, writing, speaking.
- [ ] Create `task_types` table/entity.
- [ ] Create `exam_parts` config.
- [ ] Add pass rule: `skill_score >= 9/15`.
- [ ] Add total score rule: `total_score <= 60`.
- [ ] Add timing config for each skill.
- [ ] Add A2 official task mappings.

### Suggested task types

```json
[
  {
    "skill": "listening",
    "task_types": [
      "announcement_mcq",
      "dialogue_true_false",
      "short_dialogue_missing_word"
    ]
  },
  {
    "skill": "reading",
    "task_types": [
      "short_text_statement",
      "situation_ad_matching",
      "cloze_word_choice"
    ]
  },
  {
    "skill": "writing",
    "task_types": [
      "photo_sentence",
      "word_form",
      "short_message_or_ad"
    ]
  },
  {
    "skill": "speaking",
    "task_types": [
      "interview_answer",
      "picture_description",
      "ask_question_from_card"
    ]
  }
]
```

### Validation / Acceptance Criteria

- [ ] System can represent all four A2 skills.
- [ ] Each skill has max score 15.
- [ ] Readiness logic uses minimum per-skill score, not total score only.
- [ ] Admin can view configured skills and task types.
- [ ] Learner dashboard can consume the schema.
- [ ] Existing listening tasks can be mapped into this schema.

### E2E Tests

```gherkin
Feature: A2 exam schema

Scenario: Learner sees A2 exam readiness structure
  Given a learner is logged in
  When the learner opens the dashboard
  Then the learner sees Listening, Reading, Writing, and Speaking
  And each skill shows score out of 15
  And each skill shows pass threshold 9/15

Scenario: Learner with high total but weak writing is not exam ready
  Given a learner has Listening 15, Reading 15, Speaking 15, and Writing 8
  When readiness is calculated
  Then the learner is shown "Not exam ready"
  And Writing is marked as "Risk"
```

### Analytics Events

- `exam_schema_loaded`
- `readiness_calculated`
- `skill_score_displayed`

### Definition of Done

- [ ] Schema is documented.
- [ ] Schema has seed data for A2.
- [ ] Frontend reads schema dynamically.
- [ ] E2E test confirms 9/15 rule.

---

## Epic Q1.2 — Single learner profile across exam app and listening library

**Priority:** P0
**Goal:** Connect both existing products under one learner identity and progress model.

