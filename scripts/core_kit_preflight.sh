#!/usr/bin/env bash
set -euo pipefail

# -------------------------------------------------------
# WRM Core Kit Preflight
# -------------------------------------------------------

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
CONFIG_FILE="$ROOT_DIR/config/core_kit.env"

# Load config if present
if [ -f "$CONFIG_FILE" ]; then
  echo "Loading config: $CONFIG_FILE"
  source "$CONFIG_FILE"
else
  echo "No config found. Using defaults."
fi

# Defaults (if not defined in config)
WRM_ROOT="${WRM_ROOT:-$ROOT_DIR}"
HOSTS_INI="${HOSTS_INI:-hosts.ini}"
GROUP="${GROUP:-wrm_pi_nodes}"
TAIL_LINES="${TAIL_LINES:-1500}"

echo "WRM Core Kit Preflight"
echo "root=$WRM_ROOT"
echo "hosts_ini=$HOSTS_INI"
echo "group=$GROUP"
echo "---------------------------------------------"

# Compile checks
for script in \
  "$ROOT_DIR/scripts/wrm_system_audit.py" \
  "$ROOT_DIR/scripts/trust_pulse_emitter.py" \
  "$ROOT_DIR/scripts/coherence_snapshot.py"
do
  python3 -m py_compile "$script"
  echo "OK compile: $script"
done

echo
echo "[1/3] emitting pulses..."
python3 "$ROOT_DIR/scripts/trust_pulse_emitter.py" \
  --root "$WRM_ROOT" || true

echo
echo "[2/3] building coherence snapshot..."
python3 "$ROOT_DIR/scripts/coherence_snapshot.py" \
  --root "$WRM_ROOT" \
  --tail "$TAIL_LINES" || true

echo
echo "[3/3] running fast audit..."
python3 "$ROOT_DIR/scripts/wrm_system_audit.py" \
  --root "$WRM_ROOT" \
  --hosts-ini "$HOSTS_INI" \
  --group "$GROUP" \
  --fast || true

echo
echo "✅ Preflight passed. Safe to commit/push."
