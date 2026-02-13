#!/usr/bin/env bash
set -euo pipefail

root="${1:-$HOME/wrm_dash_core}"
hosts_ini="${2:-$root/hosts.ini}"
group="${3:-wrm_pi_nodes}"

echo "WRM Core Kit Preflight"
echo "root=$root"
echo "hosts_ini=$hosts_ini"
echo "group=$group"
echo "---------------------------------------------"

py() { python3 - <<PY
import sys, py_compile
py_compile.compile("$1", doraise=True)
print("OK compile:", "$1")
PY
}

# 1) compile check
py "$root/scripts/wrm_system_audit.py"
py "$root/scripts/trust_pulse_emitter.py"
py "$root/scripts/coherence_snapshot.py"

# 2) create a small local pulse burst
echo ""
echo "[1/3] emitting pulses..."
"$root/scripts/trust_pulse_emitter.py" --root "$root" --mode wave --count 15 >/dev/null

# 3) build coherence snapshot locally
echo "[2/3] building coherence snapshot..."
"$root/scripts/coherence_snapshot.py" --root "$root" --tail 1500

# 4) run fast audit (remote)
echo "[3/3] running fast audit..."
"$root/scripts/wrm_system_audit.py" --group "$group" --hosts-ini "$hosts_ini" --root "$root" --fast >/dev/null

echo ""
echo "✅ Preflight passed. Safe to commit/push."
