#!/usr/bin/env python3
"""
trust_pulse_emitter.py — Core Kit pulse generator

Writes JSONL to:
  <root>/wrm_cortex_core/logs/trust_pulse_bus.jsonl

Optionally UDP broadcast (default 255.255.255.255:50555).

Stdlib only.
"""

from __future__ import annotations
import argparse, datetime as dt, json, os, random, socket, sys, time
from typing import Any, Dict, Optional

def utcnow() -> str:
  return dt.datetime.now(tz=dt.timezone.utc).isoformat()

def clamp01(x: float) -> float:
  return 0.0 if x < 0 else 1.0 if x > 1.0 else x

def ensure_parent(path: str) -> None:
  os.makedirs(os.path.dirname(path), exist_ok=True)

def append_jsonl(path: str, obj: Dict[str, Any]) -> None:
  ensure_parent(path)
  with open(path, "a", encoding="utf-8") as f:
    f.write(json.dumps(obj, ensure_ascii=False) + "\n")

def udp_send(host: str, port: int, payload: Dict[str, Any], broadcast: bool) -> Optional[str]:
  data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
  s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
  try:
    if broadcast:
      s.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
    s.sendto(data, (host, port))
    return None
  except Exception as e:
    return str(e)
  finally:
    try: s.close()
    except Exception: pass

def main() -> int:
  ap = argparse.ArgumentParser()
  ap.add_argument("--root", default=os.path.expanduser("~/wrm_dash_core"))
  ap.add_argument("--node", default=os.uname().nodename)
  ap.add_argument("--mode", choices=["steady","wave","random"], default="steady")
  ap.add_argument("--score", type=float, default=None)
  ap.add_argument("--direction", default=None)
  ap.add_argument("--count", type=int, default=1)
  ap.add_argument("--every-ms", type=int, default=0)
  ap.add_argument("--udp", action="store_true")
  ap.add_argument("--udp-host", default="255.255.255.255")
  ap.add_argument("--udp-port", type=int, default=50555)
  args = ap.parse_args()

  root = os.path.abspath(os.path.expanduser(args.root))
  bus = os.path.join(root, "wrm_cortex_core/logs/trust_pulse_bus.jsonl")

  base = clamp01(args.score if args.score is not None else 0.72)
  prev = base
  phase = 0.0

  def next_score() -> float:
    nonlocal base, phase
    if args.mode == "steady":
      return base
    if args.mode == "random":
      base = clamp01(base + random.uniform(-0.06, 0.06))
      return base
    # wave
    phase += 0.35
    wobble = 0.10 if (int(phase) % 2 == 0) else -0.10
    base = clamp01(base + random.uniform(-0.01, 0.01))
    return clamp01(base + wobble)

  def infer_direction(a: float, b: float) -> str:
    if args.direction:
      return args.direction
    d = b - a
    if d > 0.04: return "surging"
    if d > 0.01: return "rising"
    if d < -0.04: return "crashing"
    if d < -0.01: return "falling"
    return "steady"

  i = 0
  while True:
    cur = next_score()
    direction = infer_direction(prev, cur)
    prev = cur

    rec = {
      "ts": utcnow(),
      "node": args.node,
      "kind": "trust_pulse",
      "trust": {"score": round(float(cur), 6), "direction": direction},
      "meta": {"writer": "trust_pulse_emitter.py", "pid": os.getpid(), "host": os.uname().nodename}
    }
    append_jsonl(bus, rec)

    if args.udp:
      payload = {"ts": rec["ts"], "node": rec["node"], "score": rec["trust"]["score"], "direction": rec["trust"]["direction"]}
      err = udp_send(args.udp_host, int(args.udp_port), payload, broadcast=(args.udp_host == "255.255.255.255"))
      if err:
        print(f"[udp] send failed: {err}", file=sys.stderr)

    i += 1
    print(f"wrote pulse {i}: score={rec['trust']['score']} dir={rec['trust']['direction']} -> {bus}")

    if args.every_ms <= 0:
      if i >= args.count: break
    else:
      if i >= args.count: break
      time.sleep(max(0.0, args.every_ms / 1000.0))

  return 0

if __name__ == "__main__":
  raise SystemExit(main())
