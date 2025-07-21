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

from app.routers import transcription

# Initialize FastAPI app
app = FastAPI(
    title="Audio Transcription Service",
    description="Transcribe audio files and YouTube videos using Google Gemini API",
    version="1.0.0"
)

# Setup Jinja2 templates
templates = Jinja2Templates(directory="app/templates")

# Include routers
app.include_router(transcription.router, prefix="/api", tags=["transcription"])

@app.get("/", response_class=HTMLResponse)
async def read_root(request: Request):
    """Render the main page with upload forms."""
    return templates.TemplateResponse("index.html", {"request": request})

@app.get("/health")
async def health_check():
    """Health check endpoint for monitoring."""
    return {"status": "healthy", "service": "transcription-api"}