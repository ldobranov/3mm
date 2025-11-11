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

## 📋 Prerequisites

Before installing, ensure you have the following installed on your system:

- **Python 3.8 or higher** (check with `python --version` or `python3 --version`)
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

**Note:** The frontend's API base URL is set in `frontend/.env`. For local development, it should point to `http://localhost:8887`. If you need to connect to a different backend (e.g., production), update the `VITE_API_BASE_URL` variable in that file.

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
