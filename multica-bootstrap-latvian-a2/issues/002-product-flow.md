[Frontend] Productize learner exam flow and hide debug views

Tasks:
1. Rename learner-facing UI from Studio to Exam Simulator.
2. Hide developer/debug panels by default: Markdown, JSON, TTS, Images, Quality.
3. Add learner flow: welcome, candidate details, instructions, listening, reading, writing, speaking, results.
4. Add real simulation mode and practice mode.
5. Implement real mode restrictions: locked order, no answer key exposure, no casual section switching, auto-submit on timer end.
6. Improve result page with skill scores, pass/fail per skill, total out of 60, weak areas, next-practice suggestions.

Acceptance criteria:
- Normal learner cannot access answer keys or debug panels.
- Real simulation mode creates exactly one attempt flow.
- Practice mode allows section-level practice/review.
- UI has basic accessibility labels and keyboard navigation.
- Include tests for mode switching, timer expiry, and results rendering.
