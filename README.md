# 3mm — Мултифункционална платформа с FastAPI и Vue 3

Проектът **3mm** има за цел да бъде модулна система, която позволява лесно добавяне на функционалности като блог, онлайн магазин, домашна автоматизация и индустриален мониторинг чрез динамични добавки (extensions).

## 🛠 Стек

- **Backend:** FastAPI + Pydantic + SQLite
- **Frontend:** Vue 3 + Vite + TailwindCSS
- **UI Framework:** TailwindCSS (преди Bootstrap)
- **Системни модули:** 
  - User Manager (с роли)
  - Settings мениджър
  - Dynamic Menu Editor
  - Extension Generator (в разработка)

## Local development

On Linux, macOS or WSL, start the backend and frontend together from the
repository root:

```bash
./dev.sh
```

The script creates an isolated Python environment, installs missing
dependencies, starts the Core API on `http://localhost:8887`, waits for its
health check and then starts the web interface on `http://localhost:5173`.
Press `Ctrl+C` to stop both processes.

Run the quality checks separately:

```bash
backend/.venv/bin/python -m pip install -r backend/requirements-dev.txt
backend/.venv/bin/python -m pytest
npm --prefix frontend run build
```

### Standalone Agent development

Run one Agent from the repository root with an isolated persistent identity:

```bash
backend/.venv/bin/python -m agent \
  --data-dir .runtime/agent \
  --name local-agent \
  --role standalone
```

The Agent listens on `http://127.0.0.1:8890` by default. Its liveness,
identity contract and privacy-conscious inventory are available at:

- `/health`;
- `/ready`;
- `/api/v1/agent/hello`;
- `/api/v1/agent/inventory`.

Start two independent mock Agents with persistent, different identities:

```bash
./dev-agents.sh
```

The mock Agents listen on ports `8890` and `8891`. Their runtime data stays in
the ignored `.runtime/agents` directory, so restarting the launcher preserves
their device IDs. The first Agent reports the deterministic `mock-pi3` hardware
profile and the second reports `mock-zero2`; neither profile imports Raspberry
libraries. Press `Ctrl+C` to stop both processes.

Select a profile for an individual development Agent with
`--hardware-profile native|mock-pi3|mock-zero2|mock-linux` or the
`THREE_MM_AGENT_HARDWARE_PROFILE` environment variable. The default is
`native`. Mock profiles currently provide only the implemented
`hardware.inventory` capability; GPIO capabilities are introduced in their
own later milestone.

### Headless setup prototype

Start the browser-based setup service from the repository root:

```bash
backend/.venv/bin/python -m setup_service
```

On Windows, use `backend/.venv/Scripts/python -m setup_service`. The prototype
listens on `http://127.0.0.1:8895` by default and exposes the setup page at
`/setup`. It uses the deterministic mock network adapter: it exercises setup,
validation, commit and rollback behavior but does not inspect or change the
host's NetworkManager configuration.

The setup service also responds to common Android, Apple and Windows captive
portal probe paths by redirecting the browser to `/setup`. Its public API is
limited to versioned status and configuration endpoints under `/api/v1/setup`.

Provisioning state is written atomically under the shared provisioning data
directory (`$XDG_DATA_HOME/3mm/setup` or `$HOME/.local/share/3mm/setup` by
default). Use setup's `--data-dir`, Agent's `--provisioning-data-dir` or the
shared `THREE_MM_PROVISIONING_DATA_DIR` variable to override it. The older
`THREE_MM_SETUP_DATA_DIR` variable remains a compatibility fallback. The
journal never stores the network name or passphrase. A completed setup is
restored after a service restart; an interrupted attempt rolls back through
the network adapter and returns to setup mode.

At Agent startup, a completed provisioning snapshot overrides the fallback
`--role`. Changing the snapshot from Standalone to Hub or Node does not alter
the Agent data directory or its persistent device identity. Missing or
incomplete provisioning state leaves the explicit fallback role unchanged;
corrupt state fails startup instead of being silently replaced.

The Linux platform layer includes a read-only NetworkManager inspector. It
queries only general service state and device interface/type/state fields; it
does not query connection profiles, SSIDs, UUIDs, addresses or credentials.
The mock adapter remains the only adapter authorized for configuration changes.

The shared runtime planner maps the persisted device role to services without
depending on systemd: an unprovisioned or interrupted device runs Setup, a Node
runs Agent, and Hub or Standalone runs Core, Web plus the local Agent.
Installers and service managers can consume this plan while keeping role policy
in one tested location.

Validated systemd templates for that layout live under `deployment/systemd`.
Core is reachable from the trusted local network; Agent and Setup remain on
loopback. The templates are not installed automatically and currently grant no
NetworkManager write access to the setup prototype.

For static-artifact smoke tests, `python -m three_mm_web --directory
frontend/dist` serves the already built Vue application with history-route
fallback. It is a dependency-free validation server, not the final production
TLS or reverse-proxy boundary.

For an explicitly prepared Linux release archive, the reviewed systemd
installer is `deployment/install-systemd.sh`. It requires root, an immutable
release ID and an exact frontend CORS origin. An existing Agent identity may be
passed as the fourth argument for migration. The installer enables Core, Web
and Agent for Standalone, keeps Setup disabled, and does not alter networking
or firewall configuration.

## 📋 Prerequisites

Before installing, ensure you have the following installed on your system:

- **Python 3.10 or higher** (check with `python --version` or `python3 --version`)
  - On Ubuntu/Debian: `sudo apt update && sudo apt install python3 python3-venv python3-pip`
  - On macOS: Install from python.org or use Homebrew: `brew install python`
  - On Windows: Download from python.org (ensure "Add Python to PATH" during installation)
- **Node.js 20 or higher** (check with `node --version`)
  - Download from nodejs.org or use package manager
  - Update npm if needed: `npm install -g npm@latest`
- **npm 10 or higher** (check with `npm --version`)
  - Comes with Node.js 20+, or update with the command above

### Troubleshooting Python Virtual Environment

If you encounter errors like "cannot execute: required file not found" when activating venv or running pip:

1. Ensure Python 3.8+ is installed: `python3 --version`
2. On Linux systems, install the venv module: `sudo apt install python3-venv` (Ubuntu/Debian)
3. Try recreating the virtual environment: `rm -rf backend/venv && python3 -m venv backend/venv`
4. If `python3` doesn't work, try `python` (but ensure it's Python 3)

## 📦 Installation

### Backend Setup

1. Navigate to the backend directory:
   ```bash
   cd backend
   ```

2. Create a virtual environment:
   - On Linux/Mac:
     ```bash
     python3 -m venv venv
     ```
   - On Windows:
     ```bash
     python -m venv venv
     ```

3. Activate the virtual environment:
   - On Linux/Mac:
     ```bash
     source venv/bin/activate
     ```
   - On Windows:
     ```bash
     venv\Scripts\activate
     ```

4. Install Python dependencies:
   ```bash
   pip install -r requirements.txt
   ```

5. Initialize the database (creates admin user and initial data):
   ```bash
   python backend/scripts/init_database.py
   ```

6. (Optional) Deactivate the virtual environment when done:
   ```bash
   deactivate
   ```

### Frontend Setup

1. Navigate to the frontend directory:
   ```bash
   cd frontend
   ```

2. Install Node.js dependencies:
   ```bash
   npm install
   ```

## 🚀 Running the Application

### Backend - Quick Start (Recommended)

**Option 1: Automated Setup (First Time)**
```bash
./start_backend.sh
```
This script will:
- Create virtual environment if it doesn't exist
- Install all dependencies
- Start the server with hot reload
- Display helpful status messages

**Option 2: Quick Start (Subsequent Runs)**
```bash
./quick_start.sh
```
Use this after initial setup to quickly start the server.

**Option 3: Manual Setup**
```bash
# Activate virtual environment if not already active
source backend/venv/bin/activate  # Linux/Mac
# or
venv\Scripts\activate  # Windows

# Start the FastAPI server
uvicorn backend.main:app --reload --host 0.0.0.0 --port 8887
```

### Frontend

From the project root directory:

```bash
cd frontend
npm run dev
```

The frontend will typically run on `http://localhost:5173` (Vite default) and is configured to connect to the backend at `http://localhost:8887`.

**Note:** The frontend and backend URLs are configured in the root `config.json` file. For local development, the defaults are `http://localhost:8887` for backend and `http://localhost:5173` for frontend. If you need to connect to different URLs (e.g., production), update the `config.json` file before starting the application.

### Running Both

Open two terminal windows/tabs:

1. Terminal 1: Run `./start_backend.sh` (or manual setup)
2. Terminal 2: Run `cd frontend && npm run dev`

The application should now be accessible at the frontend URL, communicating with the backend API.

## 🔧 Development Tools

For development, you can install additional tools:
```bash
source backend/venv/bin/activate
pip install -r backend/requirements-dev.txt
```

This includes tools like:
- `httpx` - API testing
- `debugpy` - VSCode remote debugging
- `ipython` - Enhanced Python shell
- `black`, `isort` - Code formatting
- `pytest` - Testing framework

## 🛠 Common Issues and Solutions

### Python Import Issues
If you get `ModuleNotFoundError: No module named 'backend'`:
- The startup scripts automatically fix this
- Manually: ensure you're running from project root and virtual environment is active
- Run `export PYTHONPATH="${PYTHONPATH}:$(pwd)"` if needed

### Virtual Environment Issues
If `python3 -m venv` fails:
- Ubuntu/Debian: `sudo apt install python3-venv`
- Make sure you have Python 3.8+: `python3 --version`

### Permission Issues (Linux/Mac)
```bash
# Make scripts executable
chmod +x start_backend.sh
chmod +x quick_start.sh
```

### Port Already in Use
If port 8887 is busy:
```bash
# Find process using the port
lsof -i :8887
# Kill the process
kill -9 <PID>
# Or use a different port
uvicorn backend.main:app --reload --host 0.0.0.0 --port 8888
```

## 📡 Server Endpoints

- **Backend API:** http://0.0.0.0:8887
- **API Documentation:** http://0.0.0.0:8887/docs
- **Frontend:** http://localhost:5173 (typically)
