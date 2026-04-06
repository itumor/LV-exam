# ElevenLabs Batch Run Status

Run timestamp:

- `2026-04-06 13:02:45 EEST`

Script used:

- [regenerate_exam_audio_elevenlabs.py](/Users/eramadan/GitRepo/lvcodex/scripts/regenerate_exam_audio_elevenlabs.py)

Model and output format:

- `eleven_v3`
- `mp3_44100_128`

## What was done

The ElevenLabs batch generation was started for all mock exams in a clean shell.

Completed successfully:

- `A2_Mock_Exam_01`: all 6 ElevenLabs MP3 files generated
- `A2_Mock_Exam_02`: all 6 ElevenLabs MP3 files generated

Partially completed:

- `A2_Mock_Exam_03`: 4 files generated
  - `klausisanas_1_uzdevums_elevenlabs.mp3`
  - `klausisanas_2_uzdevums_elevenlabs.mp3`
  - `klausisanas_3_uzdevums_elevenlabs.mp3`
  - `runasana_1_jautajumi_elevenlabs.mp3`

Markdown files switched to ElevenLabs audio:

- [A2_Mock_Exam_01.md](/Users/eramadan/GitRepo/lvcodex/codex/A2_Mock_Exam_01.md)
- [A2_Mock_Exam_02.md](/Users/eramadan/GitRepo/lvcodex/codex/A2_Mock_Exam_02.md)

## What was not done

Not completed because the API quota ran out:

- `A2_Mock_Exam_03`
  - `runasana_2_jautajumi_elevenlabs.mp3`
  - `runasana_3_jautajumi_elevenlabs.mp3`
- `A2_Mock_Exam_04` to `A2_Mock_Exam_10`
  - no ElevenLabs MP3 files generated in this run

Markdown files not switched:

- `A2_Mock_Exam_03.md`
- `A2_Mock_Exam_04.md`
- `A2_Mock_Exam_05.md`
- `A2_Mock_Exam_06.md`
- `A2_Mock_Exam_07.md`
- `A2_Mock_Exam_08.md`
- `A2_Mock_Exam_09.md`
- `A2_Mock_Exam_10.md`

These files still point to the existing Piper MP3s.

## API failure

The run stopped with this ElevenLabs API error:

```text
quota_exceeded
This request exceeds your quota of 10000. You have 7 credits remaining, while 311 credits are required for this request.
```

The failure happened during:

- `A2_Mock_Exam_03`
- file: `runasana_2_jautajumi_elevenlabs.mp3`

## Current recommendation

- Buy more ElevenLabs credits or upgrade the plan
- Rerun the ElevenLabs script starting from Exam 3
- Only switch markdown files after a given exam has all 6 ElevenLabs MP3 files present
