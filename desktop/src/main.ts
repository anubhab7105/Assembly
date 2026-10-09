import { Command } from '@tauri-apps/plugin-shell';

async function startBackend() {
  const statusEl = document.getElementById('status')!;
  const errorEl = document.getElementById('error')!;
  const loaderEl = document.getElementById('loader')!;
  const logLinkEl = document.getElementById('log-link')!;

  let fullLogs = '';
  
  logLinkEl.onclick = () => {
    // Open logs or show them
    alert("Backend Logs:\n\n" + fullLogs.substring(fullLogs.length - 1000));
  };

  statusEl.innerText = 'Starting backend sidecar...';

  try {
    const command = Command.sidecar('binaries/backend');
    
    let port = '';
    let token = '';

    command.on('close', data => {
      console.log(`command finished with code ${data.code} and signal ${data.signal}`);
      if (!port) {
        loaderEl.style.display = 'none';
        statusEl.style.display = 'none';
        errorEl.style.display = 'block';
        errorEl.innerText = `Backend exited prematurely (Code: ${data.code})`;
        logLinkEl.style.display = 'block';
      }
    });

    command.on('error', error => {
      console.error(`command error: "${error}"`);
      loaderEl.style.display = 'none';
      statusEl.style.display = 'none';
      errorEl.style.display = 'block';
      errorEl.innerText = `Failed to start backend sidecar: ${error}`;
      logLinkEl.style.display = 'block';
    });

    command.stdout.on('data', line => {
      fullLogs += line + '\n';
      console.log(`backend: ${line}`);
      if (line.includes('ASSEMBLY_PORT=')) {
        port = line.split('ASSEMBLY_PORT=')[1].trim();
      }
      if (line.includes('ASSEMBLY_TOKEN=')) {
        token = line.split('ASSEMBLY_TOKEN=')[1].trim();
      }
    });

    command.stderr.on('data', line => {
      fullLogs += line + '\n';
      console.error(`backend stderr: ${line}`);
    });

    const child = await command.spawn();
    
    // Wait for port and token
    statusEl.innerText = 'Waiting for configuration...';
    let attempts = 0;
    while ((!port || !token) && attempts < 100) {
      await new Promise(r => setTimeout(r, 100));
      attempts++;
    }

    if (!port || !token) {
      throw new Error("Failed to get port or token from backend within 10 seconds.");
    }

    statusEl.innerText = `Backend running on port ${port}. Waiting for /health...`;

    // Wait for health
    attempts = 0;
    let healthy = false;
    while (attempts < 60 && !healthy) {
      try {
        const res = await fetch(`http://127.0.0.1:${port}/health`);
        if (res.ok) {
          healthy = true;
          break;
        }
      } catch (e) {
        // Ignore and retry
      }
      await new Promise(r => setTimeout(r, 500));
      attempts++;
    }

    if (!healthy) {
      throw new Error("Backend did not become healthy within 30 seconds.");
    }

    statusEl.innerText = 'Loading frontend...';
    
    // We want to navigate to the static frontend.
    // Assuming the frontend files are copied into a directory we can access.
    // If we use standard Tauri, we can navigate to the local URL.
    
    // Make sure we kill the backend on normal exit.
    window.addEventListener('beforeunload', () => {
      fetch(`http://127.0.0.1:${port}/shutdown`, {
        method: 'POST',
        headers: {
          'Authorization': `Bearer ${token}`
        },
        keepalive: true
      }).catch(console.error);
    });

    window.location.href = `/frontend/index.html?port=${port}&token=${token}`;

  } catch (err: any) {
    loaderEl.style.display = 'none';
    statusEl.style.display = 'none';
    errorEl.style.display = 'block';
    errorEl.innerText = err.toString();
    logLinkEl.style.display = 'block';
  }
}

startBackend();
