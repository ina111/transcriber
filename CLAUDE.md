# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

Transcriber is a multi-interface tool that transcribes audio files and YouTube videos using Google Gemini API. Available as both a CLI tool and web application with FastAPI backend. The tool outputs three formats: raw transcription, formatted text, and summary.

## Development Commands

```bash
# Install dependencies with uv
uv sync

# Run CLI tool
uv run transcriber.main:main <file_path|youtube_url>

# Run web server locally
uv run uvicorn app.main:app --reload --host 0.0.0.0 --port 8000

# Run tests
uv run pytest tests/

# Install in development mode
uv pip install -e .
```

## Architecture

### Module Structure
The codebase follows a hybrid architecture supporting both CLI and web interfaces:

#### Core Transcription Engine
- **transcriber/main.py**: CLI interface using Click, rich UI, progress display, main orchestration
- **transcriber/audio.py**: Audio processing (file validation, YouTube download via yt-dlp, audio splitting with pydub)
- **transcriber/gemini.py**: Gemini API client with retry logic, rate limiting, and cost tracking
- **transcriber/config.py**: Configuration management, environment variables, prompt templates, data models

#### Web Application
- **app/main.py**: FastAPI application with HTML interface and API endpoints
- **app/routers/transcription.py**: REST API endpoints for transcription services
- **app/templates/index.html**: Web UI for file upload and YouTube URL input
- **api/index.py**: Vercel serverless function entry point

#### Deployment & Utilities
- **run_web.py**: Local web server runner
- **run_simple.py**: Simplified CLI runner
- **test_web.py**: Web application testing

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
2. Audio extraction/conversion with FFmpeg
3. Audio splitting for long files (>30min segments)
4. Parallel API processing with rate limiting and retry logic
5. Result consolidation and multi-format output generation
6. Cost tracking and usage analytics

## Key Dependencies

### Core Transcription
- `google-generativeai`: Gemini API integration
- `yt-dlp`: YouTube audio extraction  
- `pydub`: Audio manipulation and splitting
- `ffmpeg-python`: Audio processing backend

### CLI Interface
- `click`: CLI framework
- `rich`: Enhanced terminal UI with progress bars and spinners
- `python-dotenv`: Environment configuration

### Web Application
- `fastapi`: Modern web framework with automatic API docs
- `uvicorn`: ASGI server for FastAPI
- `jinja2`: Template engine for HTML rendering
- `python-multipart`: File upload support
- `websockets`: Real-time communication

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

## Deployment Options

### Web Application (Vercel)
- Configured with `vercel.json` for serverless deployment
- Entry point: `api/index.py`
- Supports file uploads and YouTube URLs via web interface

### CLI Application
- Installable package via `pip install -e .`
- Entry point: `transcriber` command
- Supports local and Docker deployment

## Output Format

Creates three files per input:
- `{input_name}_raw.txt`: Direct transcription
- `{input_name}_formatted.txt`: Cleaned and readable
- `{input_name}_summary.txt`: Key points summary

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
- CORS configured for web deployment

## Performance Features

- Parallel processing of audio segments
- Rate limiting for API compliance
- Cost tracking with USD/JPY conversion
- Progress indicators for both CLI and web interfaces
- Efficient memory management for large audio files