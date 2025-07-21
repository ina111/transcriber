import traceback
import sys
import os

try:
    from app.main import app
except Exception as e:
    # Create a simple debug app if main import fails
    from fastapi import FastAPI
    app = FastAPI()
    
    @app.get("/")
    def debug_root():
        return {
            "error": "Import failed",
            "message": str(e),
            "traceback": traceback.format_exc(),
            "python_path": sys.path,
            "current_dir": os.getcwd(),
            "files": os.listdir(".")
        }