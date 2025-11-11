#!/bin/bash

# Color codes
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

echo -e "${BLUE}⚡ Quick Backend Test (No Venv Setup)${NC}"

# Change to project root directory
cd "$(dirname "$0")"

# Check if we're already in the right directory
if [ ! -d "backend" ]; then
    echo -e "${RED}❌ Error: backend directory not found. Run this from project root.${NC}"
    exit 1
fi

# Check if virtual environment exists
if [ -d "backend/venv" ]; then
    echo -e "${GREEN}✅ Virtual environment found${NC}"
else
    echo -e "${RED}❌ No virtual environment found.${NC}"
    echo -e "${YELLOW}Run ./start_backend.sh first to set up the full environment.${NC}"
    exit 1
fi

# Create necessary directories
mkdir -p backend/logs
mkdir -p backend/data

echo -e "${GREEN}🔥 Starting FastAPI server (reload mode)...${NC}"
echo -e "${BLUE}📡 Server: http://0.0.0.0:8887${NC}"
echo -e "${BLUE}📖 Docs: http://0.0.0.0:8887/docs${NC}"
echo ""

# Start the server using the virtual environment
backend/venv/bin/uvicorn backend.main:app --reload --host 0.0.0.0 --port 8887