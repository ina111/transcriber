import os
import sys

try:
    from app.main import app
    print("Successfully imported app from app.main")
except ImportError as e:
    print(f"Failed to import app.main: {e}")
    # Fallback to debug app
    from fastapi import FastAPI
    app = FastAPI()
    
    @app.get("/")
    def debug_root():
        return {
            "error": "Failed to import main app",
            "message": str(e),
            "current_dir": os.getcwd(),
            "app_folder_exists": os.path.exists("app"),
            "app_folder_contents": os.listdir("app") if os.path.exists("app") else "No app folder"
        }