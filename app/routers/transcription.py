"""
API endpoints for audio transcription services.
Handles file uploads and YouTube URL processing.
"""

from fastapi import APIRouter, UploadFile, File, Form, HTTPException, BackgroundTasks
from fastapi.responses import JSONResponse
import os
import tempfile
import logging
from typing import Dict, Any, List
import asyncio
from pathlib import Path
import time
from datetime import datetime

# Import the existing transcriber modules
from transcriber.audio import AudioProcessor, InputType
from transcriber.gemini import GeminiClient
from transcriber.config import TranscriptionResult, AudioSegment, load_config, ProcessingError
from app.deployment_config import get_deployment_config, handle_serverless_limitations, ensure_directories
import re

# Setup logging
logger = logging.getLogger(__name__)

# Create router
router = APIRouter()

# Initialize components
config = load_config()
deployment_config = get_deployment_config()
ensure_directories()  # Ensure required directories exist
audio_processor = AudioProcessor()

def load_prompt(name: str) -> str:
    """Load prompt from file."""
    prompt_file = Path("prompts") / f"{name}.txt"
    if not prompt_file.exists():
        logger.warning(f"Prompt file not found: {prompt_file}")
        return ""
    
    with open(prompt_file, 'r', encoding='utf-8') as f:
        return f.read().strip()

def get_safe_youtube_filename(title: str, uploader: str = "") -> str:
    """Generate safe filename for YouTube videos."""
    # Replace invalid filename characters
    safe_title = re.sub(r'[<>:"/\\|?*]', '_', title)
    safe_title = safe_title.strip().replace(' ', '_')
    
    if uploader:
        safe_uploader = re.sub(r'[<>:"/\\|?*]', '_', uploader)
        safe_uploader = safe_uploader.strip().replace(' ', '_')
        # Truncate long titles
        if len(safe_title) > 50:
            safe_title = safe_title[:50]
        return f"{safe_uploader}_{safe_title}"
    else:
        # No uploader info
        if len(safe_title) > 60:
            safe_title = safe_title[:60]
        return safe_title

async def process_transcription(
    audio_segments: List[AudioSegment],
    input_source: str,
    input_type: InputType,
    api_key_override: str = None
) -> TranscriptionResult:
    """Process audio segments and return transcription results."""
    
    # Initialize Gemini client with API key priority: override > environment > config
    api_key = api_key_override or os.getenv("GEMINI_API_KEY") or config.get("gemini_api_key")
    
    if not api_key:
        raise ProcessingError("Gemini API key not configured. Please set your API key.")
    
    gemini_client = GeminiClient(api_key, config.get("gemini_model", "gemini-2.0-flash-exp"))
    
    # Load prompts
    transcribe_prompt = load_prompt("transcribe")
    format_prompt = load_prompt("format")
    summarize_prompt = load_prompt("summarize")
    
    # Track timing
    start_time = time.time()
    
    # Calculate total audio duration
    total_duration = sum(segment.end_time - segment.start_time for segment in audio_segments)
    
    # Transcribe audio segments
    if len(audio_segments) == 1:
        # Single segment - process directly
        segment_text = await gemini_client.transcribe_audio(
            audio_segments[0].file_path,
            transcribe_prompt
        )
        audio_segments[0].transcription = segment_text
        raw_text = segment_text
    else:
        # Multiple segments - process in parallel
        tasks = []
        for i, segment in enumerate(audio_segments):
            task = gemini_client.transcribe_audio(
                segment.file_path,
                transcribe_prompt
            )
            tasks.append((i, task))
        
        # Execute all tasks concurrently
        results = await asyncio.gather(*[task for _, task in tasks])
        
        # Assign results to segments
        for (i, _), text in zip(tasks, results):
            audio_segments[i].transcription = text
        
        # Combine all transcriptions
        raw_text = "\n\n".join(
            segment.transcription for segment in audio_segments
            if segment.transcription
        )
    
    # Format text
    formatted_text = await gemini_client.format_text(raw_text, format_prompt)
    
    # Generate summary
    summary_text = await gemini_client.summarize_text(formatted_text, summarize_prompt)
    
    # Calculate processing time
    processing_time = time.time() - start_time
    
    # Create result
    result = TranscriptionResult(
        input_source=input_source,
        input_type=input_type,
        raw_text=raw_text,
        formatted_text=formatted_text,
        summary_text=summary_text,
        processing_time=processing_time,
        audio_duration=total_duration,
        segments_count=len(audio_segments),
        created_at=datetime.now()
    )
    
    return result

@router.post("/transcribe/file")
async def transcribe_audio_file(
    background_tasks: BackgroundTasks,
    audio_file: UploadFile = File(...),
    api_key_override: str = Form(None)
) -> Dict[str, Any]:
    """
    Handle audio file upload and transcription.
    
    Args:
        audio_file: Uploaded audio file
        
    Returns:
        Transcription results including raw, formatted, and summary text
    """
    temp_file_path = None
    
    try:
        # Check file size for serverless limitations
        content = await audio_file.read()
        await audio_file.seek(0)  # Reset file pointer
        
        try:
            handle_serverless_limitations(len(content))
        except ValueError as e:
            raise HTTPException(status_code=413, detail=str(e))
        
        # Validate file type
        allowed_extensions = {'.mp3', '.wav', '.m4a', '.mp4', '.webm', '.ogg', '.flac'}
        file_ext = Path(audio_file.filename).suffix.lower()
        
        if file_ext not in allowed_extensions:
            raise HTTPException(
                status_code=400,
                detail=f"Unsupported file type: {file_ext}. Allowed types: {', '.join(allowed_extensions)}"
            )
        
        # Save uploaded file to temporary location (use deployment config for temp dir)
        with tempfile.NamedTemporaryFile(
            delete=False, 
            suffix=file_ext, 
            dir=deployment_config["temp_dir"]
        ) as temp_file:
            temp_file_path = temp_file.name
            temp_file.write(content)
        
        logger.info(f"Processing uploaded file: {audio_file.filename}")
        
        # Process the audio file
        audio_path, input_type = audio_processor.process_input(temp_file_path)
        audio_segments = audio_processor.split_audio_if_needed(audio_path)
        
        # Transcribe audio segments
        result = await process_transcription(
            audio_segments,
            audio_file.filename,
            input_type,
            api_key_override
        )
        
        # Clean up temporary audio segments
        background_tasks.add_task(cleanup_temp_files, audio_segments)
        
        # Generate base filename (without extension)
        base_filename = Path(audio_file.filename).stem
        
        return {
            "status": "success",
            "raw_text": result.raw_text,
            "formatted_text": result.formatted_text,
            "summary_text": result.summary_text,
            "processing_time": result.processing_time,
            "audio_duration": result.audio_duration,
            "segments_count": result.segments_count,
            "base_filename": base_filename
        }
        
    except Exception as e:
        logger.error(f"Error processing file upload: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))
        
    finally:
        # Clean up the uploaded file
        if temp_file_path:
            background_tasks.add_task(safe_cleanup_file, temp_file_path)

@router.post("/transcribe/youtube")
async def transcribe_youtube_url(
    background_tasks: BackgroundTasks,
    youtube_url: str = Form(...),
    api_key_override: str = Form(None)
) -> Dict[str, Any]:
    """
    Handle YouTube URL transcription.
    
    Args:
        youtube_url: YouTube video URL
        
    Returns:
        Transcription results including raw, formatted, and summary text
    """
    try:
        # Check system capabilities first
        import shutil
        ffmpeg_available = shutil.which("ffmpeg") is not None
        
        # If in Vercel environment and ffmpeg is not available, provide alternative
        if deployment_config.get("is_serverless") and not ffmpeg_available:
            logger.error("YouTube processing not available in current environment: ffmpeg not found")
            raise HTTPException(
                status_code=422,
                detail="YouTube処理は現在のサーバー環境ではサポートされていません。\n\n代替手段:\n1. YouTube動画の音声を手動でMP3ファイルとしてダウンロード\n2. ダウンロードしたMP3ファイルを「音声ファイル」タブからアップロード\n\n推奨ツール: y2mate.com, youtube-dl, または類似のYouTube音声ダウンロードサービス"
            )
        
        # Validate YouTube URL
        if not any(domain in youtube_url for domain in ['youtube.com', 'youtu.be']):
            raise HTTPException(
                status_code=400,
                detail="Invalid YouTube URL. Please provide a valid YouTube video URL."
            )
        
        logger.info(f"Processing YouTube URL: {youtube_url}")
        
        try:
            # Process the YouTube URL
            audio_path, input_type = audio_processor.process_input(youtube_url)
            
        except ProcessingError as e:
            logger.error(f"YouTube processing error: {str(e)}")
            error_message = str(e)
            
            # Provide more specific error messages for common issues
            if "yt-dlp" in error_message.lower():
                error_message = "YouTube download failed. This may be due to video restrictions or temporary server issues."
            elif "network" in error_message.lower() or "connection" in error_message.lower():
                error_message = "Network connection error while downloading YouTube video."
            elif "ffmpeg" in error_message.lower():
                error_message = "Audio processing error. This video format may not be supported in the current environment."
            
            raise HTTPException(status_code=422, detail=error_message)
            
        except Exception as e:
            logger.error(f"Unexpected error during YouTube processing: {str(e)}")
            raise HTTPException(
                status_code=500, 
                detail="Failed to download YouTube video. Please check the URL and try again."
            )
        
        # Split audio if needed
        try:
            audio_segments = audio_processor.split_audio_if_needed(audio_path)
        except Exception as e:
            logger.error(f"Audio splitting error: {str(e)}")
            raise HTTPException(
                status_code=500,
                detail="Failed to process downloaded audio. The video may be too long or in an unsupported format."
            )
        
        # Transcribe audio segments
        result = await process_transcription(
            audio_segments,
            youtube_url,
            input_type,
            api_key_override
        )
        
        # Clean up temporary audio segments
        background_tasks.add_task(cleanup_temp_files, audio_segments)
        
        # Generate base filename for YouTube videos
        # Extract from audio_processor's stored info
        base_filename = "youtube_video"
        if hasattr(audio_processor, 'youtube_info') and audio_processor.youtube_info:
            youtube_info = audio_processor.youtube_info
            title = youtube_info.get('title', 'Unknown')
            uploader = youtube_info.get('uploader', '')
            base_filename = get_safe_youtube_filename(title, uploader)
        
        return {
            "status": "success",
            "raw_text": result.raw_text,
            "formatted_text": result.formatted_text,
            "summary_text": result.summary_text,
            "processing_time": result.processing_time,
            "audio_duration": result.audio_duration,
            "segments_count": result.segments_count,
            "base_filename": base_filename
        }
        
    except HTTPException:
        # Re-raise HTTP exceptions as-is
        raise
        
    except Exception as e:
        logger.error(f"Unexpected error processing YouTube URL: {str(e)}", exc_info=True)
        raise HTTPException(
            status_code=500, 
            detail=f"Server error while processing YouTube video: {str(e)}"
        )

def safe_cleanup_file(file_path: str):
    """Safely clean up a single file."""
    try:
        if file_path and os.path.exists(file_path):
            os.unlink(file_path)
            logger.debug(f"Cleaned up file: {file_path}")
    except (OSError, FileNotFoundError):
        # File already deleted or doesn't exist - this is fine
        logger.debug(f"File already cleaned up or doesn't exist: {file_path}")
    except Exception as e:
        logger.warning(f"Unexpected error cleaning up file {file_path}: {e}")

def cleanup_temp_files(audio_segments):
    """Clean up temporary audio segment files."""
    if not audio_segments:
        return
        
    for segment in audio_segments:
        try:
            if hasattr(segment, 'file_path') and segment.file_path and os.path.exists(segment.file_path):
                os.unlink(segment.file_path)
                logger.debug(f"Cleaned up temporary file: {segment.file_path}")
        except (OSError, FileNotFoundError) as e:
            # File already deleted or doesn't exist - this is fine
            logger.debug(f"File already cleaned up or doesn't exist: {segment.file_path}")
        except Exception as e:
            logger.warning(f"Unexpected error cleaning up file {segment.file_path}: {e}")
    
    # Also clean up the parent directory if it's empty
    try:
        if audio_segments and hasattr(audio_segments[0], 'file_path') and audio_segments[0].file_path:
            parent_dir = os.path.dirname(audio_segments[0].file_path)
            if parent_dir and os.path.exists(parent_dir):
                # Check if directory is empty
                if not os.listdir(parent_dir):
                    os.rmdir(parent_dir)
                    logger.debug(f"Cleaned up temporary directory: {parent_dir}")
    except (OSError, FileNotFoundError):
        # Directory already deleted - this is fine
        logger.debug("Directory already cleaned up")
    except Exception as e:
        logger.warning(f"Unexpected error cleaning up directory: {e}")

@router.post("/validate-api-key")
async def validate_api_key(api_key: str = Form(...)):
    """Validate Gemini API key."""
    try:
        from google.generativeai import configure, GenerativeModel
        
        # Test the API key
        configure(api_key=api_key)
        model = GenerativeModel("gemini-2.0-flash-exp")
        
        # Simple test prompt
        response = model.generate_content("Hello")
        
        if response.text:
            return {"status": "valid", "message": "API key is valid"}
        else:
            return {"status": "invalid", "message": "API key validation failed"}
            
    except Exception as e:
        logger.error(f"API key validation error: {str(e)}")
        return {"status": "invalid", "message": f"Invalid API key: {str(e)}"}

@router.get("/check-api-key")
async def check_api_key():
    """Check if API key is configured."""
    api_key = config.get("gemini_api_key") or os.getenv("GEMINI_API_KEY")
    return {
        "configured": bool(api_key),
        "source": "environment" if api_key else "none"
    }

@router.get("/health")
async def health_check():
    """Health check endpoint for the transcription service."""
    api_key = config.get("gemini_api_key") or os.getenv("GEMINI_API_KEY")
    return {
        "status": "healthy",
        "service": "transcription-router",
        "gemini_configured": bool(api_key),
        "environment": deployment_config["environment"],
        "is_serverless": deployment_config["is_serverless"],
        "max_file_size_mb": deployment_config["max_file_size"] / 1024 / 1024,
        "temp_dir": deployment_config["temp_dir"]
    }

@router.get("/debug/system")
async def debug_system():
    """Debug system capabilities for YouTube processing."""
    import subprocess
    import shutil
    
    # Check ffmpeg availability
    ffmpeg_available = shutil.which("ffmpeg") is not None
    ffmpeg_path = shutil.which("ffmpeg") if ffmpeg_available else "Not found"
    
    # Check yt-dlp functionality
    yt_dlp_working = False
    yt_dlp_error = ""
    try:
        import yt_dlp
        # Test with a simple YouTube URL (just info extraction, no download)
        test_url = "https://www.youtube.com/watch?v=jNQXAC9IVRw"  # Famous test video
        ydl_opts = {
            'quiet': True,
            'no_warnings': True,
        }
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(test_url, download=False)
            if info and info.get('title'):
                yt_dlp_working = True
    except Exception as e:
        yt_dlp_error = str(e)
    
    return {
        "environment": {
            "is_vercel": os.getenv("VERCEL") == "1",
            "current_dir": os.getcwd(),
            "temp_dir": deployment_config["temp_dir"]
        },
        "ffmpeg": {
            "available": ffmpeg_available,
            "path": ffmpeg_path
        },
        "yt_dlp": {
            "working": yt_dlp_working,
            "error": yt_dlp_error if not yt_dlp_working else None
        },
        "capabilities": {
            "youtube_processing": yt_dlp_working and ffmpeg_available,
            "audio_file_processing": True,
            "recommended_approach": "audio_file_only" if not (yt_dlp_working and ffmpeg_available) else "full_support"
        }
    }