#!/usr/bin/env bash
set -e

# ==============================================================================
# Bollinger Bands Options Trading Dashboard PRO - 1-Line Launcher
# Backend Port: 8001 | Frontend Port: 5174
# ==============================================================================

PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
BACKEND_DIR="${PROJECT_ROOT}/backend"
FRONTEND_DIR="${PROJECT_ROOT}/frontend"

# Colors
GREEN='\033[0;32m'
CYAN='\033[0;36m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m' # No Color

echo -e "${CYAN}================================================================${NC}"
echo -e "${CYAN}   🚀 Bollinger Bands Options Trading Dashboard PRO (NSE)       ${NC}"
echo -e "${CYAN}   Setups 1, 3, 2, 4 (CE & PE) • Zero-Token Persistence         ${NC}"
echo -e "${CYAN}================================================================${NC}"

# 1. Kill stale processes on ports 8001 and 5174
kill_port() {
  local port=$1
  local pids=$(lsof -ti :${port} 2>/dev/null || true)
  if [ -n "$pids" ]; then
    echo -e "${YELLOW}Freeing up port ${port} (PID: ${pids})...${NC}"
    kill -9 ${pids} 2>/dev/null || true
    sleep 1
  fi
}

kill_port 8001
kill_port 5174

# 2. Python environment detection
PYTHON_EXEC=""
if [ -f "${PROJECT_ROOT}/venv/bin/python3" ]; then
  PYTHON_EXEC="${PROJECT_ROOT}/venv/bin/python3"
elif [ -f "${PROJECT_ROOT}/../SSCREENER/venv/bin/python3" ]; then
  PYTHON_EXEC="${PROJECT_ROOT}/../SSCREENER/venv/bin/python3"
elif command -v python3 &>/dev/null; then
  PYTHON_EXEC="python3"
else
  echo -e "${RED}Error: Python 3 not found.${NC}"
  exit 1
fi

echo -e "${GREEN}Using Python: ${PYTHON_EXEC}${NC}"

# Cleanup on exit
cleanup() {
  echo -e "\n${YELLOW}Shutting down Bollinger Options Dashboard...${NC}"
  if [ -n "${BACKEND_PID}" ]; then
    kill -9 "${BACKEND_PID}" 2>/dev/null || true
  fi
  if [ -n "${FRONTEND_PID}" ]; then
    kill -9 "${FRONTEND_PID}" 2>/dev/null || true
  fi
  exit 0
}
trap cleanup SIGINT SIGTERM EXIT

# 3. Start Backend
echo -e "${CYAN}Starting FastAPI Backend on http://localhost:8001...${NC}"
cd "${BACKEND_DIR}"
${PYTHON_EXEC} -m uvicorn app.main:app --host 0.0.0.0 --port 8001 --reload &
BACKEND_PID=$!

# Wait for backend health
echo -n "Waiting for backend to become ready..."
for i in {1..20}; do
  if curl -s http://localhost:8001/api/health | grep -q "healthy"; then
    echo -e " ${GREEN}[Ready]${NC}"
    break
  fi
  sleep 0.5
  echo -n "."
done

# 4. Start Frontend
echo -e "${CYAN}Starting Vite Frontend on http://localhost:5174...${NC}"
cd "${FRONTEND_DIR}"
npm run dev -- --port 5174 --host &
FRONTEND_PID=$!

echo -e "\n${GREEN}================================================================${NC}"
echo -e "${GREEN}   ✨ Dashboard successfully running!                          ${NC}"
echo -e "${GREEN}   👉 Frontend:  http://localhost:5174                         ${NC}"
echo -e "${GREEN}   👉 API Docs:  http://localhost:8001/docs                    ${NC}"
echo -e "${GREEN}================================================================${NC}"
echo -e "Press [Ctrl+C] to stop all services.\n"

wait
