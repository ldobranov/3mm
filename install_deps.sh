#!/bin/bash

# Quick dependency installer for the virtual environment
echo "🔧 Installing backend dependencies..."

# Change to project root
cd "$(dirname "$0")"

# Check if virtual environment exists
if [ ! -d "backend/venv" ]; then
    echo "📦 Creating virtual environment..."
    cd backend
    python3 -m venv venv
    cd ..
fi

# Activate virtual environment and install dependencies
source backend/venv/bin/activate
echo "✅ Virtual environment activated"

# Upgrade pip first
pip install --upgrade pip

# Install dependencies
echo "📚 Installing dependencies..."
pip install -r backend/requirements.txt

# Verify installation
echo "🔍 Verifying installation..."
python3 -c "
import sys
try:
    import fastapi
    import uvicorn
    import sqlalchemy
    import user_agents
    print('✅ All critical dependencies are installed')
    print(f'   FastAPI: {fastapi.__version__}')
except ImportError as e:
    print(f'❌ Missing dependency: {e}')
    sys.exit(1)
"

echo "🎉 Setup complete! You can now run the backend with:"
echo "   uvicorn backend.main:app --reload --host 0.0.0.0 --port 8887"