"""
Vercel serverless function entry point for FastAPI application.
This file is detected by Vercel to run the FastAPI app as a serverless function.
"""

from app.main import app

# Vercel expects to find an 'app' variable in api/index.py
# This exports our FastAPI instance for Vercel to use
__all__ = ["app"]