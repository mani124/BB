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
echo -e "${CYAN}   Setups 1, 2, 3, 4 (CE & PE) • Zero-Token Persistence         ${NC}"
echo -e "${CYAN}================================================================${NC}"

# 1. Kill stale processes on ports 8001 and 5174
kill_port() {
  local port=$1
  local pids=$(lsof -ti :${port} 2>/dev/null || true)
  if [ -n "$pids" ]; then
    echo -e "${YELLOW}Freeing up port ${port} (PID: ${pids})...${NC}"
    kill -15 ${pids} 2>/dev/null || true
    sleep 0.5
    local remaining=$(lsof -ti :${port} 2>/dev/null || true)
    if [ -n "$remaining" ]; then
      kill -9 ${remaining} 2>/dev/null || true
      sleep 0.5
    fi
  fi
}

kill_port 8001
kill_port 5174

# 2. Python environment detection and verification
VENV_PATH="/Users/manigopal/Documents/SSCREENER/venv"
if [ ! -f "${VENV_PATH}/bin/python3" ]; then
  if [ -f "${PROJECT_ROOT}/venv/bin/python3" ]; then
    VENV_PATH="${PROJECT_ROOT}/venv"
  elif [ -f "${PROJECT_ROOT}/../SSCREENER/venv/bin/python3" ]; then
    VENV_PATH="${PROJECT_ROOT}/../SSCREENER/venv"
  fi
fi

if [ ! -f "${VENV_PATH}/bin/python3" ]; then
  echo -e "${RED}Error: Python virtual environment not found at /Users/manigopal/Documents/SSCREENER/venv or ${PROJECT_ROOT}/venv.${NC}"
  exit 1
fi
PYTHON_EXEC="${VENV_PATH}/bin/python3"
echo -e "${GREEN}Using Python: ${PYTHON_EXEC} ($(${PYTHON_EXEC} --version))${NC}"

# 3. Node & NPM verification
if ! command -v node &>/dev/null; then
  echo -e "${RED}Error: Node.js is not installed or not in PATH.${NC}"
  exit 1
fi

if ! command -v npm &>/dev/null; then
  echo -e "${RED}Error: npm is not installed or not in PATH.${NC}"
  exit 1
fi

echo -e "${GREEN}Using Node: $(node -v) | npm: $(npm -v)${NC}"

# Ensure frontend dependencies are installed
if [ ! -d "${FRONTEND_DIR}/node_modules" ]; then
  echo -e "${YELLOW}node_modules not found in frontend. Running npm install...${NC}"
  (cd "${FRONTEND_DIR}" && npm install)
fi

# Cleanup on exit or signals
BACKEND_PID=""
FRONTEND_PID=""

cleanup() {
  echo -e "\n${YELLOW}Shutting down Bollinger Options Dashboard services...${NC}"
  trap - SIGINT SIGTERM EXIT
  if [ -n "${BACKEND_PID}" ] && kill -0 "${BACKEND_PID}" 2>/dev/null; then
    echo -e "Stopping backend process (${BACKEND_PID})..."
    kill -15 "${BACKEND_PID}" 2>/dev/null || true
  fi
  if [ -n "${FRONTEND_PID}" ] && kill -0 "${FRONTEND_PID}" 2>/dev/null; then
    echo -e "Stopping frontend process (${FRONTEND_PID})..."
    kill -15 "${FRONTEND_PID}" 2>/dev/null || true
  fi
  sleep 1
  kill_port 8001
  kill_port 5174
  echo -e "${GREEN}All services cleanly stopped.${NC}"
  exit 0
}
trap cleanup SIGINT SIGTERM EXIT

# 4. Start FastAPI Backend on port 8001
echo -e "${CYAN}Starting FastAPI Backend on http://localhost:8001...${NC}"
cd "${BACKEND_DIR}"
${PYTHON_EXEC} -m uvicorn app.main:app --host 0.0.0.0 --port 8001 --reload &
BACKEND_PID=$!

# Wait for backend health
echo -n "Waiting for backend to become ready..."
BACKEND_READY=false
for i in {1..30}; do
  if curl -s http://localhost:8001/api/health 2>/dev/null | grep -q "healthy"; then
    echo -e " ${GREEN}[Ready]${NC}"
    BACKEND_READY=true
    break
  fi
  sleep 0.5
  echo -n "."
done

if [ "$BACKEND_READY" = false ]; then
  echo -e "\n${RED}Warning: Backend health check timed out.${NC}"
fi

# 5. Start Vite Frontend on port 5174
echo -e "${CYAN}Starting Vite Frontend on http://localhost:5174...${NC}"
cd "${FRONTEND_DIR}"
npm run dev -- --port 5174 --host &
FRONTEND_PID=$!

echo -e "\n${GREEN}================================================================${NC}"
echo -e "${GREEN}   ✨ Bollinger Options Dashboard successfully running!         ${NC}"
echo -e "${GREEN}   👉 Frontend:  http://localhost:5174                         ${NC}"
echo -e "${GREEN}   👉 API Docs:  http://localhost:8001/docs                    ${NC}"
echo -e "${GREEN}================================================================${NC}"
echo -e "Press [Ctrl+C] to stop all services.\n"

wait
