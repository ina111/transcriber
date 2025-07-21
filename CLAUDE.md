# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

Transcriber is a CLI tool that transcribes audio files and YouTube videos using Google Gemini API. The tool outputs three formats: raw transcription, formatted text, and summary.

## Development Commands

```bash
# Install dependencies with uv
uv sync

# Run the tool
uvx transcriber.py <file_path|youtube_url>

# Run with uv during development
uv run main.py

# Install in development mode
uv pip install -e .
```

## Architecture

### Module Structure
The codebase follows a layered architecture:

- **transcriber/main.py**: CLI interface using Click, progress display, main orchestration
- **transcriber/audio.py**: Audio processing (file validation, YouTube download via yt-dlp, audio splitting with pydub)
- **transcriber/gemini.py**: Gemini API client with retry logic and rate limiting
- **transcriber/config.py**: Configuration management, environment variables, prompt templates, data models

### Key Data Models
```python
@dataclass
class TranscriptionResult:
    input_source: str          # File path or URL
    input_type: InputType      # FILE or YOUTUBE
    raw_text: str             # Direct transcription
    formatted_text: str       # Cleaned and formatted
    summary_text: str         # Summarized content
    processing_time: float
    audio_duration: float
    segments_count: int
    created_at: datetime

@dataclass  
class AudioSegment:
    segment_id: int
    start_time: float
    end_time: float
    file_path: str
    transcription: str
```

### Processing Flow
1. Input validation (file vs YouTube URL)
2. Audio extraction/conversion
3. Audio splitting for long files (>15min segments)
4. Parallel API processing with rate limiting
5. Result consolidation and output generation

## Key Dependencies

- `google-generativeai`: Gemini API integration
- `yt-dlp`: YouTube audio extraction  
- `pydub`: Audio manipulation and splitting
- `click`: CLI framework
- `python-dotenv`: Environment configuration

## Configuration

### Environment Variables (.env)
```bash
GEMINI_API_KEY=your_api_key_here
GEMINI_MODEL=gemini-2.5-flash
MAX_AUDIO_DURATION=1800  # 30 minutes
RETRY_COUNT=5
RETRY_DELAY=1
OUTPUT_DIR=./output
TEMP_DIR=./temp
```

### Prompt Templates (prompts/)
- `transcribe.txt`: Audio transcription prompt
- `format.txt`: Text formatting prompt  
- `summarize.txt`: Text summarization prompt

## Output Format

Creates three files per input:
- `{input_name}_raw.txt`: Direct transcription
- `{input_name}_formatted.txt`: Cleaned and readable
- `{input_name}_summary.txt`: Key points summary

## Implementation Phases

Current implementation follows this progression:
1. **Phase 1-2 (MVP)**: Basic transcription, Gemini integration, CLI interface
2. **Phase 3**: YouTube support, multiple outputs, external prompts  
3. **Phase 4**: Long audio splitting, enhanced error handling, packaging

## Error Handling Strategy

Custom exception hierarchy:
- `TranscriberError`: Base exception
- `InputValidationError`: Invalid files/URLs
- `APIError`: Gemini API issues
- `ProcessingError`: Audio processing failures

Implements exponential backoff retry (1s to 64s, max 5 attempts) for transient failures.

## Security Considerations

- API keys managed via environment variables only
- Temporary files automatically cleaned up
- Sensitive data masked in logs
- Secure temporary directory usage