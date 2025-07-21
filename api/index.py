from fastapi import FastAPI
import os
import sys

# Create a minimal debug app
app = FastAPI()

@app.get("/")
def debug_root():
    return {
        "status": "FastAPI is working",
        "current_dir": os.getcwd(),
        "files": os.listdir("."),
        "python_path": sys.path[:5],  # First 5 entries only
        "env_vars": dict(os.environ)
    }

@app.get("/debug")
def debug_info():
    return {
        "message": "Debug endpoint working",
        "cwd": os.getcwd(),
        "listdir": os.listdir(".") if os.path.exists(".") else "no current dir"
    }