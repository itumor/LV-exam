# Privacy Policy

## Summary

Latvian A2 Exam Studio collects only the data needed to run practice exams, score responses, and provide support for paid access.

This policy describes the current product behavior and the intended production posture.

## Data Collected

- Candidate name or code if the learner enters it.
- Exam selections, answers, and attempt history.
- Objective scoring results and AI scoring metadata.
- Operational logs needed to run the service and investigate errors.

## How Data Is Used

- Deliver the exam experience.
- Store and resume attempts.
- Generate scores and practice feedback.
- Detect abuse, fraud, and repeated failures.
- Support billing and account access once those features are enabled.

## What We Do Not Need

- Full identity documents.
- Unnecessary profile data.
- Answer keys exposed to ordinary users.
- Provider API keys in the browser.

## Storage And Security

- Secrets live in the server environment or secret store.
- Production deployments should use HTTPS.
- Access should be rate limited where scoring or login costs money.
- Backups should be enabled once submissions are stored in a database.

## Retention

- Prototype data may remain in browser localStorage until server persistence is added.
- Server-side submissions should be retained only as long as needed for product support, billing, and compliance.
- Deletion requests should remove or anonymize learner data once the platform supports account deletion.

## Sharing

We do not sell learner data. Data may be shared only with service providers required to run the product, such as hosting, email, payment, or scoring vendors.

## Contact

Publish the final support contact and data deletion process alongside the production deployment.
