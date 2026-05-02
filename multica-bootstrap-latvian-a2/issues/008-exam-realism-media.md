[Exam Realism] Add speaking recording, upload, playback controls, and PDF report

Tasks:
1. Add stricter real simulation controls: no pause, auto-submit on timeout, one final submit per section/attempt.
2. Add optional listening playback count tracking.
3. Add browser microphone recording for speaking tasks.
4. Upload speaking audio to object storage.
5. Add playback for review and optional speech-to-text path.
6. Add candidate-style report and PDF export.

Acceptance criteria:
- Real simulation timer behavior is deterministic.
- Speaking recording works with permission handling and failure states.
- Audio upload uses signed URLs or secure server-mediated upload.
- Candidate report includes total score, skill scores, pass/fail, corrections, recommendations, and disclaimer.
- Tests cover timeout, upload failure, and report generation.
