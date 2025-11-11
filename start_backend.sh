#!/bin/bash

# Color codes for better output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

echo -e "${BLUE}🚀 Starting 3mm Backend Server${NC}"

# Change to project root directory
cd "$(dirname "$0")"

# Check if virtual environment exists
if [ ! -d "backend/venv" ]; then
    echo -e "${YELLOW}📦 Virtual environment not found. Creating one...${NC}"
    cd backend
    python3 -m venv venv
    cd ..
else
    echo -e "${GREEN}✅ Virtual environment found${NC}"
fi

# Activate virtual environment
echo -e "${YELLOW}🔧 Using virtual environment...${NC}"

# Install/update dependencies using venv pip directly
echo -e "${YELLOW}📚 Installing/Updating dependencies...${NC}"
backend/venv/bin/pip install -r backend/requirements.txt

# Check for critical dependencies
echo -e "${YELLOW}🔍 Checking critical dependencies...${NC}"
python3 -c "import fastapi, uvicorn, sqlalchemy, user_agents" 2>/dev/null
if [ $? -ne 0 ]; then
    echo -e "${RED}❌ Critical dependencies missing. Please check the error above.${NC}"
    exit 1
fi

echo -e "${GREEN}✅ All dependencies are available${NC}"

# Create necessary directories
mkdir -p backend/logs
mkdir -p backend/data

# Check database
if [ ! -f "backend/mega_monitor.db" ]; then
    echo -e "${YELLOW}🗄️ Database not found. Will be created on first run.${NC}"
fi

# Run the FastAPI server
echo -e "${GREEN}🔥 Starting FastAPI server...${NC}"
echo -e "${BLUE}📡 Server will be available at: http://0.0.0.0:8887${NC}"
echo -e "${BLUE}📖 API Documentation: http://0.0.0.0:8887/docs${NC}"
echo -e "${YELLOW}Press Ctrl+C to stop the server${NC}"
echo ""

# Start the server using the virtual environment
backend/venv/bin/uvicorn backend.main:app --reload --host 0.0.0.0 --port 8887