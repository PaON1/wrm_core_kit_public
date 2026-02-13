#!/usr/bin/env python3
"""
wrm_system_audit.py — WRM Core Kit audit (stable)

- Reads hosts.ini group
- SSH reachability + identity
- Root auto-probe (handles /home/on1 vs /home/<user>)
- Core-kit log presence + sizes
- WRM-ish systemd services (system + user)

Stdlib only.
"""

from __future__ import annotations
import argparse, dataclasses, json, os, shlex, subprocess, datetime as dt
from typing import Any, Dict, List, Optional

CORE_LOG_PATHS = [
  "wrm_cortex_core/logs/trust_pulse_bus.jsonl",
  "wrm_cortex_core/logs/trust_fields.jsonl",
  "wrm_cortex_core/logs/state/promote_bus.state.json",
  "wrm_mesh/logs/vote_bus/received_trust_pulses.jsonl",
  "freezer/logs/freezer_events.jsonl",
]

WRM_KEYWORDS = ["wrm","freezer","mesh","trust","glyph","pulse","hub","socket","helix","bus","shipper","decision","worker"]

DEFAULT_SSH_OPTS = [
  "-o","BatchMode=yes",
  "-o","StrictHostKeyChecking=accept-new",
  "-o","ConnectTimeout=4",
  "-o","ServerAliveInterval=5",
  "-o","ServerAliveCountMax=1",
  "-o","PreferredAuthentications=publickey",
]

MAX_COUNT_MB = 256.0  # if a jsonl file is larger, we skip line counting

def utcnow() -> str:
  return dt.datetime.now(tz=dt.timezone.utc).isoformat()

@dataclasses.dataclass
class HostEntry:
  host: str
  ansible_user: Optional[str] = None
  ansible_host: Optional[str] = None
  ansible_port: Optional[int] = None

def parse_hosts_ini_group(path: str, group: str) -> List[HostEntry]:
  if not os.path.exists(path):
    raise FileNotFoundError(f"hosts file not found: {path}")
  entries: List[HostEntry] = []
  in_group = False
  header = f"[{group}]"
  with open(path, "r", encoding="utf-8", errors="replace") as f:
    for raw in f:
      line = raw.strip()
      if not line or line.startswith("#") or line.startswith(";"):
        continue
      if line.startswith("[") and line.endswith("]"):
        in_group = (line == header)
        continue
      if not in_group:
        continue
      parts = line.split()
      name = parts[0]
      kv: Dict[str,str] = {}
      for p in parts[1:]:
        if "=" in p:
          k,v = p.split("=",1)
          kv[k.strip()] = v.strip()
      entries.append(HostEntry(
        host=name,
        ansible_user=kv.get("ansible_user"),
        ansible_host=kv.get("ansible_host"),
        ansible_port=int(kv["ansible_port"]) if kv.get("ansible_port","").isdigit() else None
      ))
  # de-dupe
  seen=set(); out=[]
  for e in entries:
    if e.host not in seen:
      seen.add(e.host); out.append(e)
  return out

def run_local(cmd: List[str], timeout_s: int = 15) -> subprocess.CompletedProcess:
  return subprocess.run(cmd, capture_output=True, text=True, timeout=timeout_s, check=False)

def run_ssh(ent: HostEntry, remote_cmd: str, timeout_s: int, ssh_user: Optional[str], identity_file: Optional[str], port: Optional[int]) -> subprocess.CompletedProcess:
  target_host = ent.ansible_host or ent.host
  user = ssh_user or ent.ansible_user
  prt = port or ent.ansible_port
  target = f"{user}@{target_host}" if user else target_host

  cmd = ["ssh", *DEFAULT_SSH_OPTS]
  if identity_file:
    cmd += ["-i", identity_file]
  if prt:
    cmd += ["-p", str(prt)]
  cmd += [target, "--", "bash", "-lc", remote_cmd]
  try:
    return run_local(cmd, timeout_s=timeout_s)
  except subprocess.TimeoutExpired:
    # mimic completed process on timeout
    cp = subprocess.CompletedProcess(cmd, 124, "", f"timeout after {timeout_s}s")
    return cp

def filter_wrm_units(raw: str) -> List[str]:
  out=[]
  for ln in (raw or "").splitlines():
    s=ln.strip()
    if not s: continue
    low=s.lower()
    if any(k in low for k in WRM_KEYWORDS):
      out.append(s)
  return out

def collect(ent: HostEntry, root_hint: str, ssh_user: Optional[str], identity_file: Optional[str], port: Optional[int], fast: bool, oversize_mb: float) -> Dict[str,Any]:
  snap: Dict[str,Any] = {"host": ent.host, "reachable": False, "ts": utcnow(), "errors": [], "root_hint": root_hint, "root_resolved": None, "identity": None, "logs": {}, "services": {}, "oversized": []}

  # Reachability
  r = run_ssh(ent, "true", timeout_s=6, ssh_user=ssh_user, identity_file=identity_file, port=port)
  if r.returncode != 0:
    snap["errors"].append((r.stderr or r.stdout or f"ssh_exit_code={r.returncode}").strip())
    return snap
  snap["reachable"] = True

  # Identity
  ident = run_ssh(ent, "whoami; hostname", timeout_s=7, ssh_user=ssh_user, identity_file=identity_file, port=port)
  who, hostn = None, None
  lines = [x.strip() for x in (ident.stdout or "").splitlines() if x.strip()]
  if len(lines) >= 1: who = lines[0]
  if len(lines) >= 2: hostn = lines[1]
  snap["identity"] = {"whoami": who, "hostname": hostn}

  # Root candidates
  candidates=[]
  if root_hint: candidates.append(os.path.expanduser(root_hint).rstrip("/"))
  if who: candidates.append(f"/home/{who}/wrm_dash_core")
  candidates.append("/home/on1/wrm_dash_core")
  # dedupe preserve order
  seen=set(); cand=[]
  for c in candidates:
    c=c.rstrip("/")
    if c and c not in seen:
      seen.add(c); cand.append(c)

  # Probe root by hits
  probe_py = r"""
import os, sys, json
rel = [
  "wrm_cortex_core/logs/trust_pulse_bus.jsonl",
  "wrm_cortex_core/logs/trust_fields.jsonl",
  "wrm_mesh/logs/vote_bus/received_trust_pulses.jsonl",
  "freezer/logs/freezer_events.jsonl",
]
best=None; checked=[]
for root in sys.argv[1:]:
  hits=0
  for p in rel:
    if os.path.exists(os.path.join(root, p)): hits += 1
  checked.append({"root": root, "hits": hits})
  if best is None or hits > best["hits"]:
    best={"root": root, "hits": hits}
print(json.dumps({"best": best, "checked": checked}))
"""
  cmd = "python3 - <<'PY'\n" + probe_py.strip() + "\nPY\n " + " ".join(shlex.quote(x) for x in cand)
  pr = run_ssh(ent, cmd, timeout_s=10 if not fast else 7, ssh_user=ssh_user, identity_file=identity_file, port=port)
  resolved = cand[0] if cand else root_hint
  if (pr.stdout or "").strip():
    last = pr.stdout.strip().splitlines()[-1].strip()
    try:
      obj = json.loads(last)
      if isinstance(obj, dict) and isinstance(obj.get("best"), dict) and obj["best"].get("root"):
        resolved = obj["best"]["root"]
    except Exception:
      pass
  snap["root_resolved"] = resolved
  root = resolved

  # Services
  sysu = run_ssh(ent, "systemctl list-units --type=service --state=running,activating,failed --no-pager --no-legend", timeout_s=12 if not fast else 7, ssh_user=ssh_user, identity_file=identity_file, port=port)
  usru = run_ssh(ent, "systemctl --user list-units --type=service --state=running,activating,failed --no-pager --no-legend || true", timeout_s=12 if not fast else 7, ssh_user=ssh_user, identity_file=identity_file, port=port)
  snap["services"]["system_wrm"] = filter_wrm_units(sysu.stdout or "")
  snap["services"]["user_wrm"] = filter_wrm_units(usru.stdout or "")

  # Log stats
  stat_py = r"""
import os, sys, json, time
MAX_MB = float(os.environ.get("MAX_COUNT_MB","256"))
now = time.time()
out={}
for path in sys.argv[1:]:
  rec={"exists": False}
  try:
    st=os.stat(path)
    rec["exists"]=True
    rec["size_bytes"]=int(st.st_size)
    rec["mtime_ts"]=int(st.st_mtime)
    rec["mtime_age_s"]=int(now - st.st_mtime)
    mb = rec["size_bytes"]/(1024.0*1024.0)
    if path.endswith(".jsonl") and mb <= MAX_MB:
      n=0
      with open(path,"rb") as f:
        while True:
          b=f.read(1024*1024)
          if not b: break
          n += b.count(b"\n")
      rec["lines"]=int(n)
    else:
      rec["lines"]=None
      if path.endswith(".jsonl") and mb > MAX_MB:
        rec["lines_skipped_reason"]=f"size_mb>{MAX_MB}"
  except FileNotFoundError:
    pass
  except Exception as e:
    rec["error"]=str(e)
  out[path]=rec
print(json.dumps(out))
"""
  full_paths = [os.path.join(root, rel) for rel in CORE_LOG_PATHS]
  stat_cmd = f"MAX_COUNT_MB={MAX_COUNT_MB} python3 - <<'PY'\n{stat_py.strip()}\nPY\n " + " ".join(shlex.quote(p) for p in full_paths)
  st = run_ssh(ent, stat_cmd, timeout_s=22 if not fast else 12, ssh_user=ssh_user, identity_file=identity_file, port=port)
  if (st.stdout or "").strip():
    last = st.stdout.strip().splitlines()[-1].strip()
    try:
      snap["logs"]["core_stats"] = json.loads(last)
    except Exception:
      snap["logs"]["core_stats_raw"] = (st.stdout or "").strip()

  # Oversized list
  core = snap.get("logs", {}).get("core_stats", {})
  if isinstance(core, dict):
    for path, rec in core.items():
      if not (isinstance(rec, dict) and rec.get("exists")):
        continue
      mb = float(rec.get("size_bytes", 0)) / (1024.0*1024.0)
      if mb >= oversize_mb:
        snap["oversized"].append({"path": path, "size_mb": round(mb,2), "lines": rec.get("lines")})
    snap["oversized"].sort(key=lambda x: -x["size_mb"])

  return snap

def summarize(state: Dict[str,Any]) -> str:
  nodes = state["nodes"]
  reachable = [n for n in nodes if n.get("reachable")]
  lines=[]
  lines.append("WRM System Audit — Summary")
  lines.append("-"*78)
  lines.append(f"ts: {state['ts']}")
  lines.append(f"hosts: total={len(nodes)} reachable={len(reachable)} unreachable={len(nodes)-len(reachable)}")
  lines.append("")
  lines.append("identity (whoami@hostname):")
  for n in reachable:
    who = (n.get("identity") or {}).get("whoami")
    hn  = (n.get("identity") or {}).get("hostname")
    lines.append(f"  - {n['host']}: {who}@{hn}")
  lines.append("")
  lines.append("core log streams presence (count hosts where stream exists):")
  counts={rel:0 for rel in CORE_LOG_PATHS}
  for n in reachable:
    root = n.get("root_resolved") or ""
    core = (n.get("logs") or {}).get("core_stats", {})
    if not isinstance(core, dict):
      continue
    for rel in CORE_LOG_PATHS:
      full = os.path.join(root, rel)
      rec = core.get(full, {})
      if isinstance(rec, dict) and rec.get("exists"):
        counts[rel] += 1
  for rel in CORE_LOG_PATHS:
    lines.append(f"  - {rel}: {counts[rel]}/{len(reachable) if reachable else 0}")

  lines.append("")
  lines.append("WRM-ish running services (filtered):")
  for n in reachable:
    sysw = (n.get("services") or {}).get("system_wrm") or []
    usrw = (n.get("services") or {}).get("user_wrm") or []
    if sysw or usrw:
      lines.append(f"  {n['host']}:")
      for ln in sysw[:20]:
        lines.append(f"    [sys] {ln}")
      for ln in usrw[:20]:
        lines.append(f"    [usr] {ln}")

  # top oversized
  big=[]
  for n in reachable:
    for item in (n.get("oversized") or []):
      big.append({"host": n["host"], **item})
  big.sort(key=lambda x: -x.get("size_mb",0))
  lines.append("")
  lines.append("oversized flows (top 8):")
  for item in big[:8]:
    lines.append(f"  - {item['host']} {item['size_mb']}MB {item['path']}")
  return "\n".join(lines)

def main() -> int:
  ap = argparse.ArgumentParser()
  ap.add_argument("--group", default="wrm_pi_nodes")
  ap.add_argument("--hosts-ini", default=os.path.expanduser("~/wrm_dash_core/hosts.ini"))
  ap.add_argument("--root", default="~/wrm_dash_core")
  ap.add_argument("--limit", default=None, help="comma-separated hostnames")
  ap.add_argument("--fast", action="store_true")
  ap.add_argument("--ssh-user", default=None)
  ap.add_argument("--identity-file", default=None)
  ap.add_argument("--port", type=int, default=None)
  ap.add_argument("--oversize-mb", type=float, default=50.0)
  ap.add_argument("--out", default=os.path.expanduser("~/wrm_dash_core/WRM_state_snapshot.json"))
  args = ap.parse_args()

  entries = parse_hosts_ini_group(args.hosts_ini, args.group)
  if args.limit:
    allow={x.strip() for x in args.limit.split(",") if x.strip()}
    entries=[e for e in entries if e.host in allow]

  state: Dict[str,Any] = {
    "schema": "wrm.core_kit_audit.v1",
    "ts": utcnow(),
    "group": args.group,
    "hosts_ini": os.path.abspath(os.path.expanduser(args.hosts_ini)),
    "root_hint": args.root,
    "nodes": []
  }

  for ent in entries:
    state["nodes"].append(collect(ent, args.root, args.ssh_user, args.identity_file, args.port, args.fast, float(args.oversize_mb)))

  txt = summarize(state)
  state["summary_text"] = txt

  out_path = os.path.abspath(os.path.expanduser(args.out))
  os.makedirs(os.path.dirname(out_path), exist_ok=True)
  with open(out_path, "w", encoding="utf-8") as f:
    json.dump(state, f, ensure_ascii=False, indent=2)

  print(txt)
  print("")
  print(f"snapshot written: {out_path}")
  return 0

if __name__ == "__main__":
  raise SystemExit(main())
