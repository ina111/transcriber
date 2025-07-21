"""
FastAPI application main module.
Handles web interface for audio transcription service.
"""

from fastapi import FastAPI
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from fastapi.staticfiles import StaticFiles
from starlette.requests import Request
import os
from pathlib import Path

from app.routers import transcription

# Initialize FastAPI app
app = FastAPI(
    title="Audio Transcription Service",
    description="Transcribe audio files and YouTube videos using Google Gemini API",
    version="1.0.0"
)

# Setup Jinja2 templates with absolute path
BASE_DIR = Path(__file__).resolve().parent.parent
templates = Jinja2Templates(directory=str(BASE_DIR / "app" / "templates"))

# Include routers
app.include_router(transcription.router, prefix="/api", tags=["transcription"])

@app.get("/", response_class=HTMLResponse)
async def read_root(request: Request):
    """Render the main page with upload forms."""
    try:
        return templates.TemplateResponse("index.html", {"request": request})
    except Exception as e:
        return HTMLResponse(f"<h1>Service Starting...</h1><p>Error: {str(e)}</p>", status_code=500)

@app.get("/health")
async def health_check():
    """Health check endpoint for monitoring."""
    return {"status": "healthy", "service": "transcription-api"}