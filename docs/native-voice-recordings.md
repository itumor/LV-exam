# Adding Native Voice Recordings

This guide explains how to add realistic native Latvian voice recordings to the listening library.

## Overview

The Latvian A2 Listening Library supports speaker metadata to help learners practice with diverse voices. Each audio item can include information about the speaker, speaking style, and recording context.

## Adding Speaker Metadata

When adding a new audio item to the library, include speaker metadata in the JSON file. Here's an example:

```json
{
  "id": "audio_001",
  "title": "Saruna veikalā",
  "level": "A2",
  "audio_file": "shopping.mp3",
  "speaker": {
    "speakerId": "speaker_001",
    "speakerDisplayName": "Cashier",
    "voiceType": "cashier",
    "speakingStyle": "casual",
    "recordingContext": "natural"
  }
}
```

## Speaker Fields

| Field | Type | Description | Required |
|-------|------|-------------|-----------|
| `speakerId` | string | Unique identifier | No |
| `speakerDisplayName` | string | Display label (e.g., "Cashier") | Recommended |
| `voiceType` | string | Voice role category | Recommended |
| `speakingStyle` | string | How the voice speaks | No |
| `gender` | string | Speaker gender | No |
| `ageGroup` | string | Age category | No |
| `accent` | string | Regional accent | No |
| `recordingContext` | string | Recording environment | No |

## Voice Types

Use one of these supported voice types:

- `cashier` - Shop/store cashier
- `doctor` - Medical professional
- `teacher` - School teacher
- `colleague` - Office coworker
- `driver` - Public transport driver
- `grandmother` - Elderly woman
- `grandfather` - Elderly man
- `government` - Government office employee
- `friend` - Peer/friend
- `landlord` - Property owner/manager

## Speaking Styles

- `clear` - Very clear, careful pronunciation
- `slow` - Slower than normal pace
- `normal` - Standard conversation pace
- `casual` - Informal, relaxed
- `announcement` - Public announcements
- `dialogue` - Two-way conversation

## Age Groups

- `child` - Under 13
- `teen` - 13-19
- `adult` - 20-64
- `senior` - 65+

## Regional Accents

- `riga` - Riga area
- `latgale` - Latgale region
- `kurzemne` - Kurzeme region
- `vidzeme` - Vidzeme region
- `zemgale` - Zemgale region
- `standard` - Standard/broadcast

## Recording Contexts

- `studio` - Professional studio recording
- `natural` - Natural environment recording
- `outdoor` - Outdoor setting
- `classroom` - Classroom setting
- `office` - Office/workplace
- `public_space` - Public area (shop, station, etc.)

## Audio Quality Guidelines

For best learner experience:

1. **Audio Format**: MP3 at 128kbps or higher
2. **Duration**: 30 seconds to 3 minutes for A2 level
3. **Background Noise**: Minimize background noise
4. **Volume**: Consistent throughout, moderate level
5. **Clarity**: Clear enough to distinguish words

## Example: Adding a New Voice Lesson

1. Add the audio file to `data/A2_klausisanas/audio/`
2. Create the metadata JSON file in `data/A2_klausisanas/metadata/`
3. Run the build script:

```bash
python3 scripts/build_catalog.py
```

The catalog will automatically include the speaker metadata in the output.

## Backwards Compatibility

Audio items without speaker metadata will still work correctly. The UI gracefully handles missing fields.

- Missing speaker: No badge displayed
- Missing speaking style: Filter shows "All styles"
- Missing voice_type: Item excluded from voice recommendations