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
- **Node.js 16 or higher** (check with `node --version`)
- **npm** (comes with Node.js, check with `npm --version`)

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

5. (Optional) Deactivate the virtual environment when done:
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

### Backend

From the project root directory:

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

The frontend will typically run on `http://localhost:5173` (Vite default).

### Running Both

Open two terminal windows/tabs:

1. Terminal 1: Run the backend as above
2. Terminal 2: Run the frontend as above

The application should now be accessible at the frontend URL, communicating with the backend API.

## 🛠 Alternative Backend Start

You can also use the provided script (Linux/Mac only):
```bash
./start_backend.sh
```
