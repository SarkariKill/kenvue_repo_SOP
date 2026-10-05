#!/usr/bin/env python3
"""
Entrypoint for Hugging Face Spaces cloud deployment.
Starts LLM microservice (:8001) and API + Frontend service (:7860).
"""

import os
import signal
import subprocess
import sys
import time

PORT = int(os.environ.get("PORT", "7860"))
PROJECT_ROOT = os.path.dirname(os.path.abspath(__file__))

env = os.environ.copy()
env["PYTHONUNBUFFERED"] = "1"
api_path = os.path.join(PROJECT_ROOT, "services", "api")
llm_path = os.path.join(PROJECT_ROOT, "services", "llm")
existing_pythonpath = env.get("PYTHONPATH", "")
env["PYTHONPATH"] = f"{api_path}:{llm_path}:{existing_pythonpath}" if existing_pythonpath else f"{api_path}:{llm_path}"
env["STORAGE_DIR"] = os.path.join(PROJECT_ROOT, "storage")
env["DATABASE_PATH"] = os.path.join(PROJECT_ROOT, "storage", "data", "chat.db")
env["INDEX_STORAGE_PATH"] = os.path.join(PROJECT_ROOT, "storage", "indexes")
env["LLM_SERVICE_URL"] = "http://127.0.0.1:8001"

print(f"🚀 Starting Kenvue SOP Assistant on Hugging Face Spaces (Port {PORT})...")

# 1. Start LLM service in background (:8001)
llm_proc = subprocess.Popen(
    [sys.executable, "-m", "uvicorn", "services.llm.main:app", "--host", "127.0.0.1", "--port", "8001"],
    cwd=PROJECT_ROOT,
    env=env,
)

# 2. Start API Backend (:7860) which also serves the compiled React SPA
api_proc = subprocess.Popen(
    [sys.executable, "-m", "uvicorn", "services.api.main:app", "--host", "0.0.0.0", "--port", str(PORT)],
    cwd=PROJECT_ROOT,
    env=env,
)


def cleanup(sig=None, frame=None):
    try:
        api_proc.terminate()
        llm_proc.terminate()
    except Exception:
        pass
    sys.exit(0)


signal.signal(signal.SIGINT, cleanup)
signal.signal(signal.SIGTERM, cleanup)

try:
    while True:
        time.sleep(1)
        if api_proc.poll() is not None:
            llm_proc.terminate()
            sys.exit(api_proc.returncode)
        if llm_proc.poll() is not None:
            api_proc.terminate()
            sys.exit(llm_proc.returncode)
except KeyboardInterrupt:
    cleanup()
