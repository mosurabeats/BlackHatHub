#!/bin/bash
# Executive Hub launcher for macOS. Double-click in Finder (or run ./START-MAC.command).
# - Checks for Python 3.12+, creates a private virtual environment, installs dependencies
# - Creates .env from .env.example on first run
# - Migrates the database and starts the server + scheduled research workers
# - Opens your browser; prints the address for iPhone/iPad on the same Wi-Fi
# - Ctrl+C (or closing this window) shuts down gracefully
set -u
cd "$(dirname "$0")"
ROOT="$(pwd)"
VENV="$ROOT/.venv"
PORT_DEFAULT=8765

say() { printf "\033[1;32m==>\033[0m %s\n" "$*"; }
warn() { printf "\033[1;33m!!\033[0m %s\n" "$*"; }
die() { printf "\033[1;31mERROR:\033[0m %s\n" "$*"; echo; read -r -p "Press Return to close." _; exit 1; }

# ---------------------------------------------------------------- Python
find_python() {
  for c in python3.13 python3.12 /opt/homebrew/bin/python3 /usr/local/bin/python3 \
           /Library/Frameworks/Python.framework/Versions/3.13/bin/python3 \
           /Library/Frameworks/Python.framework/Versions/3.12/bin/python3 python3; do
    if command -v "$c" >/dev/null 2>&1; then
      if "$c" -c 'import sys; sys.exit(0 if sys.version_info >= (3,12) else 1)' 2>/dev/null; then
        command -v "$c"; return 0
      fi
    fi
  done
  return 1
}
PY="$(find_python)" || {
  warn "Python 3.12 or newer is required."
  if command -v brew >/dev/null 2>&1; then
    read -r -p "Install Python 3.12 with Homebrew now? [y/N] " a
    if [[ "$a" =~ ^[Yy] ]]; then brew install python@3.12 || die "Homebrew install failed"; PY="$(find_python)" || die "Python still not found"; fi
  fi
  [ -n "${PY:-}" ] || die "Install Python 3.12+ from https://www.python.org/downloads/macos/ and run this launcher again."
}
say "Using $("$PY" --version) at $PY"

# ---------------------------------------------------------------- venv + deps
if [ ! -x "$VENV/bin/python" ]; then
  say "Creating private Python environment (first run only)…"
  "$PY" -m venv "$VENV" || die "Could not create virtual environment"
fi
REQ_HASH="$(shasum -a 256 backend/requirements.txt | cut -d' ' -f1)"
if [ ! -f "$VENV/.req-hash" ] || [ "$(cat "$VENV/.req-hash")" != "$REQ_HASH" ]; then
  say "Installing dependencies…"
  "$VENV/bin/python" -m pip install --quiet --upgrade pip || die "pip upgrade failed (check internet connection)"
  "$VENV/bin/python" -m pip install --quiet -r backend/requirements.txt || die "Dependency install failed (check internet connection)"
  echo "$REQ_HASH" > "$VENV/.req-hash"
fi

# ---------------------------------------------------------------- config
if [ ! -f "$ROOT/.env" ]; then
  cp "$ROOT/.env.example" "$ROOT/.env"
  chmod 600 "$ROOT/.env"
  say "Created .env (edit it to add optional API keys)."
fi
PORT="$(grep -E '^EXECHUB_PORT=' .env 2>/dev/null | cut -d= -f2)"; PORT="${PORT:-$PORT_DEFAULT}"

# ---------------------------------------------------------------- frontend
if [ ! -f "$ROOT/frontend/dist/index.html" ]; then
  if command -v npm >/dev/null 2>&1; then
    say "Building the web interface…"
    (cd frontend && npm ci --no-audit --no-fund && npm run build) || die "Frontend build failed"
  else
    die "The prebuilt web interface (frontend/dist) is missing and Node.js is not installed. Re-download the release ZIP."
  fi
fi

# ---------------------------------------------------------------- already running?
if curl -fsS "http://127.0.0.1:$PORT/api/ping" >/dev/null 2>&1; then
  say "Executive Hub is already running."
  open "http://localhost:$PORT/"
  exit 0
fi

# ---------------------------------------------------------------- start
say "Preparing database (migrations + reference data)…"
(cd backend && "$VENV/bin/python" -m app.cli init) || die "Database initialization failed"

cd "$ROOT/backend"
# caffeinate -i keeps the Mac from idle-sleeping while the hub runs (scheduled research needs the host awake).
caffeinate -i "$VENV/bin/python" -m app.server &
SERVER_PID=$!
cleanup() {
  echo; say "Shutting down gracefully…"
  kill -INT "$SERVER_PID" 2>/dev/null
  wait "$SERVER_PID" 2>/dev/null
  say "Stopped. Your data is in $ROOT/data"
  exit 0
}
trap cleanup INT TERM HUP

for _ in $(seq 1 60); do
  curl -fsS "http://127.0.0.1:$PORT/api/ping" >/dev/null 2>&1 && break
  kill -0 "$SERVER_PID" 2>/dev/null || die "Server exited during startup (see messages above)"
  sleep 0.5
done

LAN_IP="$(ipconfig getifaddr en0 2>/dev/null || ipconfig getifaddr en1 2>/dev/null || true)"
TS_IP="$(command -v tailscale >/dev/null 2>&1 && tailscale ip -4 2>/dev/null | head -1 || true)"
echo
say "Executive Hub is running:  http://localhost:$PORT/"
[ -n "$LAN_IP" ] && say "iPhone / iPad on the same Wi-Fi:  http://$LAN_IP:$PORT/"
[ -n "$TS_IP" ] && say "Via Tailscale:  http://$TS_IP:$PORT/"
say "Keep this window open. Press Ctrl+C to stop."
open "http://localhost:$PORT/"
wait "$SERVER_PID"
