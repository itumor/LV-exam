[Content] Build structured exam bank importer and validation pipeline

Tasks:
1. Define structured exam JSON schema.
2. Build parser/importer from current Markdown mock exam format.
3. Include metadata, sections, tasks, questions, options, correct answers, audio/image assets, scoring rules.
4. Add validation checks: missing answer keys, broken audio/image links, duplicate options, unexpected point totals, missing scoring metadata.
5. Add content workflow statuses: draft, review, published, archived.

Acceptance criteria:
- Current mock exams can be imported into structured JSON.
- Validator fails clearly on broken assets or scoring inconsistencies.
- Published exams are versioned and immutable for historical attempts.
- Tests include valid exam fixture and multiple invalid fixtures.
