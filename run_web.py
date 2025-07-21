#!/usr/bin/env python3
"""
Simple script to run the web application locally for testing.
"""

import uvicorn
import os
import sys
from pathlib import Path

# Add the project root to Python path
project_root = Path(__file__).parent
sys.path.insert(0, str(project_root))

def main():
    """Run the FastAPI application."""
    # Check if .env file exists
    env_file = project_root / ".env"
    if not env_file.exists():
        print("⚠️  Warning: .env file not found!")
        print("   Make sure to set GEMINI_API_KEY environment variable")
        print()
    
    print("🚀 Starting Transcriber Web Application...")
    print("📍 Open http://localhost:8001 in your browser")
    print("📝 API docs available at http://localhost:8001/docs")
    print("🛑 Press CTRL+C to stop the server")
    print()
    
    # Run the application
    uvicorn.run(
        "app.main:app",
        host="0.0.0.0",
        port=8001,
        reload=True,
        log_level="info"
    )

if __name__ == "__main__":
    main()