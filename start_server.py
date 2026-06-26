"""Simple server starter with error handling"""
import sys
import os

# Ensure we're in the right directory
os.chdir(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, '.')

print("Starting Maker-Checker API Server...")
print(f"Python: {sys.executable}")
print(f"Working directory: {os.getcwd()}")

try:
    print("Importing app...")
    from app.main import app
    print("App imported successfully!")

    print("Starting uvicorn...")
    import uvicorn
    uvicorn.run(app, host="127.0.0.1", port=8000, log_level="info")
except Exception as e:
    print(f"Error: {e}")
    import traceback
    traceback.print_exc()
    sys.exit(1)
