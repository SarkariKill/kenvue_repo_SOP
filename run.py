#!/usr/bin/env python3
"""
=============================================================================
Kenvue SOP Optimization & RAG Assistant - Local One-Click Launcher (Docker-Free)
=============================================================================
Runs the complete full-stack application directly on your local system:
- LLM Provider Service (FastAPI) on port 8001
- Main API Backend (FastAPI + Local File Storage + FAISS HNSW) on port 8000
- Frontend Web Application (React + Vite) on port 3000
- Zero Docker / Zero MinIO dependency: all assets (images, tables, generated PDFs,
  summaries, and FAISS vector indexes) are stored directly in ./storage/

Usage:
    python3 run.py            # Standard local start (auto-installs if needed)
    python3 run.py --stop     # Stop all running local services & free ports
    python3 run.py --install  # Force re-install dependencies and start
=============================================================================
"""

import os
import signal
import shutil
import subprocess
import sys
import time
import urllib.error
import urllib.request
import webbrowser

# Terminal color codes
CYAN = "\033[96m"
GREEN = "\033[92m"
YELLOW = "\033[93m"
RED = "\033[91m"
BOLD = "\033[1m"
DIM = "\033[2m"
RESET = "\033[0m"

PROJECT_ROOT = os.path.dirname(os.path.abspath(__file__))
STORAGE_DIR = os.path.join(PROJECT_ROOT, "storage")
VENV_DIR = os.path.join(PROJECT_ROOT, ".venv")

# Track active subprocesses
ACTIVE_PROCESSES = []


def print_banner():
    banner = f"""
{CYAN}{BOLD}====================================================================
  🚀 KENVUE SOP OPTIMIZATION ASSISTANT (LOCAL DOCKER-FREE LAUNCHER)
===================================================================={RESET}
"""
    print(banner)


def free_ports(ports=(3000, 8000, 8001)):
    """Kill any existing processes occupying our target ports."""
    for port in ports:
        try:
            res = subprocess.run(
                ["lsof", "-ti", f":{port}"],
                stdout=subprocess.PIPE,
                stderr=subprocess.DEVNULL,
                text=True,
            )
            pids = res.stdout.strip().split()
            for pid in pids:
                if pid and pid != str(os.getpid()):
                    try:
                        os.kill(int(pid), signal.SIGKILL)
                        print(f"{YELLOW}Released port {port} (killed PID {pid}){RESET}")
                    except Exception:
                        pass
        except Exception:
            pass


def ensure_storage_structure():
    """Ensure local filesystem storage directories exist."""
    subfolders = [
        "images",
        "tables",
        "users",
        "templates",
        "skills",
        "data",
        "indexes",
        "artifacts",
    ]
    os.makedirs(STORAGE_DIR, exist_ok=True)
    for sub in subfolders:
        os.makedirs(os.path.join(STORAGE_DIR, sub), exist_ok=True)
    print(f"{GREEN}✓ Local storage initialized at: {STORAGE_DIR}{RESET}")


def ensure_env_file():
    """Ensure .env file exists; create from .env.example if missing."""
    env_path = os.path.join(PROJECT_ROOT, ".env")
    env_example_path = os.path.join(PROJECT_ROOT, ".env.example")
    if not os.path.exists(env_path) and os.path.exists(env_example_path):
        shutil.copy(env_example_path, env_path)
        print(f"{GREEN}✓ Created default .env file.{RESET}")


def load_env_vars():
    """Parse .env file into environment dictionary."""
    env_path = os.path.join(PROJECT_ROOT, ".env")
    env_vars = os.environ.copy()
    if os.path.exists(env_path):
        with open(env_path, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith("#") and "=" in line:
                    k, v = line.split("=", 1)
                    k = k.strip()
                    v = v.strip().strip('"').strip("'")
                    if k and k not in env_vars:
                        env_vars[k] = v
    return env_vars


def get_python_binary():
    """Return python binary inside active virtualenv or .venv."""
    # 1. If currently inside an active virtualenv (e.g. source .venv/bin/activate)
    if os.environ.get("VIRTUAL_ENV"):
        venv_py = os.path.join(os.environ["VIRTUAL_ENV"], "bin", "python")
        if os.path.exists(venv_py):
            return venv_py
    # 2. Check project .venv
    if sys.platform == "win32":
        venv_py = os.path.join(VENV_DIR, "Scripts", "python.exe")
    else:
        venv_py = os.path.join(VENV_DIR, "bin", "python")
    if os.path.exists(venv_py):
        return venv_py
    return sys.executable


def get_pip_binary():
    """Return pip binary inside active virtualenv or .venv."""
    if os.environ.get("VIRTUAL_ENV"):
        venv_pip = os.path.join(os.environ["VIRTUAL_ENV"], "bin", "pip")
        if os.path.exists(venv_pip):
            return venv_pip
    if sys.platform == "win32":
        venv_pip = os.path.join(VENV_DIR, "Scripts", "pip.exe")
    else:
        venv_pip = os.path.join(VENV_DIR, "bin", "pip")
    if os.path.exists(venv_pip):
        return venv_pip
    return shutil.which("pip") or "pip"


def check_local_environment(force_install=False):
    """Ensure Python virtual environment and Node.js dependencies are ready."""
    print(f"{CYAN}🔍 Checking local environment & dependencies...{RESET}")

    # 1. Check Node.js and npm
    if shutil.which("node") is None or shutil.which("npm") is None:
        print(f"{RED}❌ Node.js and npm are required for the frontend.{RESET}")
        print("   Please install Node.js from https://nodejs.org/")
        sys.exit(1)
    print(f"{GREEN}✓ Node.js & npm detected.{RESET}")

    # 2. Check/Create virtualenv
    python_bin = get_python_binary()
    if not os.path.exists(python_bin) or (not os.environ.get("VIRTUAL_ENV") and not os.path.exists(os.path.join(VENV_DIR, "bin", "python"))):
        print(f"{CYAN}📦 Creating Python virtual environment at .venv...{RESET}")
        base_py = sys.executable
        for candidate in ["python3.12", "python3.11", "python3.10", "python3"]:
            p = shutil.which(candidate)
            if p:
                base_py = p
                break
        res = subprocess.run([base_py, "-m", "venv", VENV_DIR])
        if res.returncode != 0:
            print(f"{RED}❌ Failed to create virtual environment.{RESET}")
            sys.exit(1)
        force_install = True
        python_bin = get_python_binary()

    print(f"{GREEN}✓ Python environment: {python_bin}{RESET}")

    # 3. Verify Python packages
    sys.stdout.write("   Checking Python backend packages... ")
    sys.stdout.flush()
    need_install = force_install
    if not need_install:
        test_code = "import fastapi, uvicorn, pymupdf"
        res = subprocess.run([python_bin, "-c", test_code], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        if res.returncode != 0:
            need_install = True

    if need_install:
        sys.stdout.write(f"{YELLOW}installing missing packages...{RESET}\n")
        print(f"{CYAN}📥 Installing backend dependencies (FastAPI, PyMuPDF, FastEmbed, ReportLab, FAISS)...{RESET}")
        pip_bin = get_pip_binary()
        api_req = os.path.join(PROJECT_ROOT, "services", "api", "requirements.txt")
        llm_req = os.path.join(PROJECT_ROOT, "services", "llm", "requirements.txt")
        subprocess.run([pip_bin, "install", "--upgrade", "pip"], stdout=subprocess.DEVNULL)
        res = subprocess.run([pip_bin, "install", "-r", api_req, "-r", llm_req])
        if res.returncode != 0:
            print(f"{RED}❌ Failed to install Python dependencies. Please check terminal output above.{RESET}")
            sys.exit(1)
        print(f"{GREEN}✓ Python dependencies installed.{RESET}")
    else:
        sys.stdout.write(f"{GREEN}READY!{RESET}\n")
        sys.stdout.flush()

    # 4. Check Frontend node_modules
    frontend_dir = os.path.join(PROJECT_ROOT, "frontend")
    node_modules = os.path.join(frontend_dir, "node_modules")
    if not os.path.exists(node_modules) or force_install:
        print(f"{CYAN}📥 Installing frontend dependencies via npm...{RESET}")
        res = subprocess.run(["npm", "install"], cwd=frontend_dir)
        if res.returncode != 0:
            print(f"{RED}❌ Failed to install npm dependencies.{RESET}")
            sys.exit(1)
        print(f"{GREEN}✓ Frontend dependencies ready.{RESET}")
    else:
        print(f"{GREEN}✓ Frontend dependencies ready.{RESET}")


def wait_for_service(url: str, service_name: str, max_retries: int = 40, delay: float = 0.8) -> bool:
    """Poll an HTTP endpoint until it returns 200/304 OK or times out."""
    sys.stdout.write(f"   ⏳ Waiting for {service_name} ({url})... ")
    sys.stdout.flush()

    for _ in range(max_retries):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "HealthCheck/1.0"})
            with urllib.request.urlopen(req, timeout=2) as resp:
                if resp.status in (200, 304):
                    sys.stdout.write(f"{GREEN}READY!{RESET}\n")
                    sys.stdout.flush()
                    return True
        except Exception:
            pass
        time.sleep(delay)
        sys.stdout.write(".")
        sys.stdout.flush()

    sys.stdout.write(f"{YELLOW}Proceeding...{RESET}\n")
    return False


def start_local_services():
    """Start LLM service, API Backend, and Frontend as local subprocesses."""
    global ACTIVE_PROCESSES
    free_ports([3000, 8000, 8001])

    python_bin = get_python_binary()
    env = load_env_vars()
    env["PYTHONUNBUFFERED"] = "1"
    env["STORAGE_DIR"] = STORAGE_DIR
    env["DATABASE_PATH"] = os.path.join(STORAGE_DIR, "data", "chat.db")
    env["INDEX_STORAGE_PATH"] = os.path.join(STORAGE_DIR, "indexes")
    env["LLM_SERVICE_URL"] = "http://localhost:8001"
    env["API_PORT"] = "8000"
    env["LLM_PORT"] = "8001"
    env["FRONTEND_PORT"] = "3000"

    print(f"\n{CYAN}🚀 Launching local services...{RESET}")

    # 1. Start LLM Service (port 8001)
    llm_dir = os.path.join(PROJECT_ROOT, "services", "llm")
    llm_cmd = [python_bin, "-m", "uvicorn", "main:app", "--host", "127.0.0.1", "--port", "8001"]
    llm_proc = subprocess.Popen(llm_cmd, cwd=llm_dir, env=env)
    ACTIVE_PROCESSES.append(("LLM Service", llm_proc))
    print(f"  • {BOLD}LLM Service{RESET} started on PID {llm_proc.pid} (:8001)")

    # 2. Start API Backend (port 8000)
    api_dir = os.path.join(PROJECT_ROOT, "services", "api")
    api_cmd = [python_bin, "-m", "uvicorn", "main:app", "--host", "127.0.0.1", "--port", "8000"]
    api_proc = subprocess.Popen(api_cmd, cwd=api_dir, env=env)
    ACTIVE_PROCESSES.append(("API Backend", api_proc))
    print(f"  • {BOLD}API Backend{RESET} started on PID {api_proc.pid} (:8000)")

    # 3. Start Frontend Web UI (port 3000)
    frontend_dir = os.path.join(PROJECT_ROOT, "frontend")
    npm_cmd = shutil.which("npm") or "npm"
    frontend_cmd = [npm_cmd, "run", "dev"]
    frontend_proc = subprocess.Popen(frontend_cmd, cwd=frontend_dir, env=env)
    ACTIVE_PROCESSES.append(("Frontend UI", frontend_proc))
    print(f"  • {BOLD}Frontend UI{RESET} started on PID {frontend_proc.pid} (:3000)")

    print(f"\n{CYAN}🔍 Verifying service health...{RESET}")
    wait_for_service("http://localhost:8001/health", "LLM Provider Service")
    wait_for_service("http://localhost:8000/health", "API Backend")
    wait_for_service("http://localhost:3000", "Frontend Web UI")


def open_browser():
    """Open default browser to http://localhost:3000."""
    frontend_url = "http://localhost:3000"
    print(f"\n{CYAN}🌐 Opening browser to {frontend_url}...{RESET}")
    try:
        webbrowser.open(frontend_url, new=2)
    except Exception as e:
        print(f"{YELLOW}⚠️ Could not open browser automatically: {e}{RESET}")
        print(f"👉 Please open {frontend_url} in your browser.")


def print_summary():
    """Print service access links, local storage status, and credentials."""
    print(f"\n{GREEN}{BOLD}🎉 ALL SERVICES ARE RUNNING LOCALLY (DOCKER-FREE)!{RESET}\n")
    print(f"{BOLD}Access Links:{RESET}")
    print(f"  • {BOLD}Web Application:{RESET}    {CYAN}http://localhost:3000{RESET}")
    print(f"  • {BOLD}API Swagger Docs:{RESET}   {CYAN}http://localhost:8000/docs{RESET}")
    print(f"  • {BOLD}LLM Microservice:{RESET}   {CYAN}http://localhost:8001{RESET}\n")
    print(f"{BOLD}Local File Storage:{RESET}")
    print(f"  • {BOLD}Storage Directory:{RESET}  {CYAN}{STORAGE_DIR}{RESET}")
    print(f"    - Images:      {DIM}{os.path.join(STORAGE_DIR, 'images')}{RESET}")
    print(f"    - Tables:      {DIM}{os.path.join(STORAGE_DIR, 'tables')}{RESET}")
    print(f"    - PDFs/Users:  {DIM}{os.path.join(STORAGE_DIR, 'users')}{RESET}")
    print(f"    - Database:    {DIM}{os.path.join(STORAGE_DIR, 'data', 'chat.db')}{RESET}")
    print(f"    - HNSW Vector: {DIM}{os.path.join(STORAGE_DIR, 'indexes')}{RESET}\n")
    print(f"{BOLD}Default Login Credentials:{RESET}")
    print(f"  • Username: {YELLOW}admin{RESET}")
    print(f"  • Password: {YELLOW}admin{RESET}  (or create a new user)\n")
    print(f"{DIM}--------------------------------------------------------------------")
    print("Application is active. Press Ctrl+C anytime to stop all services.")
    print(f"--------------------------------------------------------------------{RESET}\n")


def cleanup_and_exit(signum=None, frame=None):
    """Gracefully terminate all running subprocesses and release ports."""
    print(f"\n\n{YELLOW}🛑 Stopping all local services...{RESET}")
    for name, proc in ACTIVE_PROCESSES:
        try:
            proc.terminate()
            print(f"  • Stopped {name} (PID {proc.pid})")
        except Exception:
            pass

    time.sleep(1)
    # Ensure any remaining processes are terminated
    for name, proc in ACTIVE_PROCESSES:
        try:
            if proc.poll() is None:
                proc.kill()
        except Exception:
            pass

    free_ports([3000, 8000, 8001])
    print(f"{GREEN}✓ All services stopped cleanly. Local ports released.{RESET}\n")
    sys.exit(0)


def main():
    args = sys.argv[1:]

    if "--stop" in args or "stop" in args or "down" in args:
        print_banner()
        print(f"{YELLOW}🛑 Freeing ports 3000, 8000, 8001...{RESET}")
        free_ports([3000, 8000, 8001])
        print(f"{GREEN}✓ Ports released.{RESET}")
        return

    force_install = "--install" in args or "-i" in args

    # Register Ctrl+C / SIGINT / SIGTERM handlers
    signal.signal(signal.SIGINT, cleanup_and_exit)
    signal.signal(signal.SIGTERM, cleanup_and_exit)

    print_banner()
    ensure_env_file()
    ensure_storage_structure()
    check_local_environment(force_install=force_install)
    start_local_services()
    open_browser()
    print_summary()

    # Keep main process alive while watching child processes
    try:
        while True:
            time.sleep(1)
            for name, proc in ACTIVE_PROCESSES:
                if proc.poll() is not None:
                    print(f"{RED}⚠️ {name} exited unexpectedly with code {proc.returncode}.{RESET}")
                    cleanup_and_exit()
    except KeyboardInterrupt:
        cleanup_and_exit()


if __name__ == "__main__":
    main()
