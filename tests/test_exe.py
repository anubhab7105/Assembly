import os
import subprocess
import time
from pathlib import Path

import requests


def test_executable():
    exe_path = Path("dist/assembly_backend/assembly_backend.exe")
    if not exe_path.exists():
        print(f"Error: {exe_path} not found")
        return

    print(f"Testing {exe_path}...")
    size_mb = exe_path.stat().st_size / (1024 * 1024)
    print(f"Executable size: {size_mb:.2f} MB")
    
    start_time = time.time()
    
    # Run the executable
    env = os.environ.copy()
    env["APP_MODE"] = "desktop"
    process = subprocess.Popen(
        [str(exe_path)],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        env=env
    )
    
    port = None
    token = None
    
    # Read stdout line by line to find port and token
    print("Waiting for startup output...")
    while True:
        line = process.stdout.readline()
        if not line:
            break
        print(f"STDOUT: {line.strip()}")
        if line.startswith("ASSEMBLY_PORT="):
            port = line.strip().split("=")[1]
        elif line.startswith("ASSEMBLY_TOKEN="):
            token = line.strip().split("=")[1]
            
        if port and token:
            break
            
    startup_time = time.time() - start_time
    print(f"Startup took {startup_time:.2f} seconds")
    print(f"Captured Port: {port}, Token: {token}")
    
    if not port or not token:
        print("Failed to capture port or token. Exiting...")
        process.kill()
        return
        
    base_url = f"http://127.0.0.1:{port}"
    
    # Test /health
    print(f"Testing {base_url}/health ...")
    try:
        health_resp = requests.get(f"{base_url}/health")
        print(f"/health response: {health_resp.status_code} {health_resp.text}")
    except Exception as e:
        print(f"Failed to hit /health: {e}")
        
    # Test /shutdown
    print(f"Testing {base_url}/shutdown with token...")
    try:
        shutdown_resp = requests.post(
            f"{base_url}/shutdown",
            headers={"X-Assembly-Token": token}
        )
        print(f"/shutdown response: {shutdown_resp.status_code} {shutdown_resp.text}")
    except Exception as e:
        print(f"Failed to hit /shutdown: {e}")
        
    print("Waiting for process to exit gracefully...")
    process.wait(timeout=5)
    print(f"Process exited with code: {process.returncode}")

if __name__ == "__main__":
    test_executable()
