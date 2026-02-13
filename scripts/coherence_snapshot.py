#!/usr/bin/env python3
"""
coherence_snapshot.py — WRM Core Kit coherence snapshot (v0.3)

Goal (Core Kit):
- Be able to compute a *non-zero* coherence snapshot from the most basic stream:
  wrm_cortex_core/logs/trust_pulse_bus.jsonl

Design:
- Default source: trust_pulse_bus.jsonl (Core Kit primitive)
- Optional: trust_fields.jsonl (richer lane, but schema varies; use only when explicit)
- Tail-based reading (avoid multi-GB scans)
- Stays stdlib-only

Heuristic coherence:
- From recent pulse events, measure inter-arrival regularity per node.
- Per node: score = 1 / (1 + stddev(dt)) over last K intervals (dt in seconds)
- Global coherence = mean(node_scores) across nodes_reporting
"""

from __future__ import annotations

import argparse
import datetime as _dt
import json
import os
import statistics
import time
from typing import Any, Dict, Iterable, List, Optional, Tuple

DEFAULT_ROOT = os.path.expanduser("~/wrm_dash_core")
DEFAULT_OUT = os.path.join(DEFAULT_ROOT, "wrm_cortex_core/logs/state/coherence_snapshot.json")

DEFAULT_PULSE_SOURCE = os.path.join(DEFAULT_ROOT, "wrm_cortex_core/logs/trust_pulse_bus.jsonl")
DEFAULT_FIELDS_SOURCE = os.path.join(DEFAULT_ROOT, "wrm_cortex_core/logs/trust_fields.jsonl")

# Common identifiers seen across WRM logs
NODE_KEYS = ("node", "node_id", "host", "from", "source_node", "sender", "origin")

# Common timestamps; we accept epoch seconds, epoch ms, or ISO strings
TS_KEYS = ("ts", "timestamp", "t", "time", "emitted_ts", "created_ts")


def utcnow() -> str:
    return _dt.datetime.now(tz=_dt.timezone.utc).isoformat()


def _safe_json_loads(line: str) -> Optional[dict]:
    line = line.strip()
    if not line:
        return None
    try:
        return json.loads(line)
    except Exception:
        return None


def tail_lines(path: str, max_lines: int) -> List[str]:
    """
    Efficient-ish tail for JSONL without external commands.
    Reads from end of file in blocks until enough newlines are collected.
    """
    if max_lines <= 0:
        return []

    try:
        with open(path, "rb") as f:
            f.seek(0, os.SEEK_END)
            end = f.tell()
            if end == 0:
                return []

            block = 1024 * 1024  # 1MB
            data = b""
            pos = end
            nl = 0
            while pos > 0 and nl <= max_lines:
                read_size = block if pos >= block else pos
                pos -= read_size
                f.seek(pos)
                chunk = f.read(read_size)
                data = chunk + data
                nl = data.count(b"\n")

            # Keep only last max_lines lines
            lines = data.splitlines()[-max_lines:]
            return [ln.decode("utf-8", errors="replace") for ln in lines]
    except FileNotFoundError:
        return []
    except Exception:
        return []


def parse_ts_any(obj: dict) -> Optional[float]:
    """Return epoch seconds if possible."""
    for k in TS_KEYS:
        if k in obj:
            v = obj.get(k)
            if v is None:
                continue

            # epoch seconds or ms
            if isinstance(v, (int, float)):
                vv = float(v)
                # likely ms if too large
                if vv > 10_000_000_000:
                    vv = vv / 1000.0
                return vv

            # ISO string
            if isinstance(v, str):
                s = v.strip()
                if not s:
                    continue
                try:
                    dt = _dt.datetime.fromisoformat(s.replace("Z", "+00:00"))
                    if dt.tzinfo is None:
                        dt = dt.replace(tzinfo=_dt.timezone.utc)
                    return dt.timestamp()
                except Exception:
                    pass

    return None


def parse_node_id(obj: dict) -> Optional[str]:
    for k in NODE_KEYS:
        if k in obj:
            v = obj.get(k)
            if isinstance(v, str) and v.strip():
                return v.strip()
            if isinstance(v, (int, float)):
                return str(v)
            if isinstance(v, dict):
                # sometimes nested
                for kk in NODE_KEYS:
                    vv = v.get(kk)
                    if isinstance(vv, str) and vv.strip():
                        return vv.strip()
    return None


def pick_source(explicit: Optional[str], root: str) -> str:
    if explicit:
        return os.path.expanduser(explicit)

    # Core Kit default: pulse bus
    pulse = os.path.join(root, "wrm_cortex_core/logs/trust_pulse_bus.jsonl")
    if os.path.exists(pulse) and os.path.getsize(pulse) > 0:
        return pulse

    fields = os.path.join(root, "wrm_cortex_core/logs/trust_fields.jsonl")
    return fields


def compute_coherence_from_pulses(records: List[dict], per_node_k: int) -> Tuple[int, float, Dict[str, Any]]:
    """
    Build per-node inter-arrival deltas and compute node scores.
    """
    by_node: Dict[str, List[float]] = {}
    for r in records:
        nid = parse_node_id(r) or "unknown"
        ts = parse_ts_any(r)
        if ts is None:
            continue
        by_node.setdefault(nid, []).append(ts)

    # sort timestamps per node
    node_scores: Dict[str, float] = {}
    node_details: Dict[str, Any] = {}

    for nid, tss in by_node.items():
        if len(tss) < 3:
            continue
        tss.sort()
        dts = [tss[i] - tss[i - 1] for i in range(1, len(tss))]
        # use last K intervals
        dts = dts[-per_node_k:] if per_node_k > 0 else dts
        if len(dts) < 2:
            continue

        # stddev of inter-arrival times; smaller => more regular => higher coherence
        try:
            sd = statistics.pstdev(dts)
            mean_dt = sum(dts) / len(dts)
        except Exception:
            continue

        score = 1.0 / (1.0 + sd)
        node_scores[nid] = float(score)
        node_details[nid] = {
            "events_used": int(len(tss)),
            "intervals_used": int(len(dts)),
            "mean_dt_s": float(mean_dt),
            "std_dt_s": float(sd),
            "score": float(score),
        }

    nodes_reporting = len(node_scores)
    global_coh = float(sum(node_scores.values()) / nodes_reporting) if nodes_reporting else 0.0
    return nodes_reporting, global_coh, node_details


def main() -> int:
    ap = argparse.ArgumentParser(description="WRM Core Kit coherence snapshot")
    ap.add_argument("--root", default=DEFAULT_ROOT, help="WRM root (default: ~/wrm_dash_core)")
    ap.add_argument("--source", default=None, help="Explicit JSONL source (optional)")
    ap.add_argument("--tail", type=int, default=6000, help="Tail N lines from source (default: 6000)")
    ap.add_argument("--per-node-k", type=int, default=80, help="Use last K intervals per node (default: 80)")
    ap.add_argument("--out", default=DEFAULT_OUT, help="Output JSON path")
    args = ap.parse_args()

    root = os.path.abspath(os.path.expanduser(args.root))
    src = pick_source(args.source, root)

    lines = tail_lines(src, int(args.tail))
    recs = [_safe_json_loads(ln) for ln in lines]
    recs = [r for r in recs if isinstance(r, dict)]

    nodes_reporting, global_coherence, node_details = compute_coherence_from_pulses(recs, int(args.per_node_k))

    snap: Dict[str, Any] = {
        "schema": "wrm.coherence_snapshot.v0.3",
        "ts": utcnow(),
        "root": root,
        "source": src,
        "tail_lines": int(args.tail),
        "nodes_reporting": int(nodes_reporting),
        "global_coherence": float(round(global_coherence, 6)),
        "nodes": node_details,
        "notes": [
            "Core Kit snapshot computed from pulse inter-arrival regularity.",
            "Use --source trust_fields.jsonl only if you explicitly want that lane.",
        ],
    }

    out_path = os.path.abspath(os.path.expanduser(args.out))
    os.makedirs(os.path.dirname(out_path), exist_ok=True)
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(snap, f, ensure_ascii=False, indent=2)

    print("WRM Coherence Snapshot")
    print("-" * 72)
    print(f"ts: {snap['ts']}")
    print(f"source: {snap['source']}")
    print(f"tail_lines: {snap['tail_lines']}")
    print(f"nodes_reporting: {snap['nodes_reporting']}")
    print(f"global_coherence: {snap['global_coherence']}")
    print("")
    print(f"wrote: {out_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
