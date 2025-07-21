import os
import sys
from fastapi import FastAPI

# Force new deployment - timestamp: 2025-01-21 12:00:00
app = FastAPI()

@app.get("/")
def debug_root():
    try:
        import app.main
        return {"status": "app.main imported successfully", "timestamp": "2025-01-21 12:00:00"}
    except Exception as e:
        return {
            "error": f"Import failed: {str(e)}",
            "timestamp": "2025-01-21 12:00:00",
            "current_dir": os.getcwd(),
            "app_folder_exists": os.path.exists("app"),
            "app_folder_contents": os.listdir("app") if os.path.exists("app") else "No app folder",
            "app_main_exists": os.path.exists("app/main.py"),
            "traceback": str(e)
        }

@app.get("/test")  
def test():
    return {"message": "New deployment working", "timestamp": "2025-01-21 12:00:00"}