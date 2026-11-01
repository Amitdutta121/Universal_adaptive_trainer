#!/usr/bin/env bash
# Attribute file changes to Claude Code sessions.
# Usage: blame-sessions.sh <repo-relative-or-abs-path> [more paths...]
# Scans session transcripts (~/.claude/projects/<slug>/*.jsonl) for Edit/Write/
# MultiEdit tool calls touching each path, and prints which session(s) did it.
# Read-only. Ignores this session's own id (the watcher).
set -uo pipefail
cd "$(git rev-parse --show-toplevel)" || exit 1

SELF="${CLAUDE_SESSION_ID:-}"
[ -z "$SELF" ] && [ -f .claude/watcher/self-session-id ] && SELF="$(tr -d '[:space:]' < .claude/watcher/self-session-id)"
HOURS="${WATCHER_BLAME_HOURS:-24}"

python - "$SELF" "$HOURS" "$@" <<'PY'
import json, os, sys, glob, time
from datetime import datetime, timezone

self_id = sys.argv[1]
hours   = float(sys.argv[2])
targets = [os.path.normcase(os.path.abspath(p)) for p in sys.argv[3:]]
if not targets:
    print("(no paths given)"); sys.exit(0)

home = os.path.expanduser("~")
roots = glob.glob(os.path.join(home, ".claude", "projects", "*FInalAdaptiveTrainer*"))
cutoff = time.time() - hours * 3600

# path -> session -> {count, first_ts, last_ts}
hits = {t: {} for t in targets}
sess_meta = {}   # session -> {first_user, cwd, file}

for root in roots:
    for f in glob.glob(os.path.join(root, "*.jsonl")):
        if os.path.getmtime(f) < cutoff:
            continue
        sid = os.path.splitext(os.path.basename(f))[0]
        try:
            fh = open(f, encoding="utf-8")
        except OSError:
            continue
        with fh:
            for line in fh:
                try:
                    d = json.loads(line)
                except Exception:
                    continue
                sid_l = d.get("sessionId") or d.get("session_id") or sid
                if sid_l not in sess_meta:
                    sess_meta[sid_l] = {"first_user": None, "cwd": d.get("cwd"), "file": f}
                msg = d.get("message") or {}
                content = msg.get("content")
                # capture first human prompt as a label
                if (sess_meta[sid_l]["first_user"] is None
                        and d.get("type") == "user" and isinstance(content, str)
                        and not content.startswith("<")):
                    sess_meta[sid_l]["first_user"] = content.strip().replace("\n", " ")[:90]
                if not isinstance(content, list):
                    continue
                for b in content:
                    if not (isinstance(b, dict) and b.get("type") == "tool_use"):
                        continue
                    inp = b.get("input", {}) or {}
                    ts = d.get("timestamp")
                    name = b.get("name")

                    if name in ("Edit", "Write", "MultiEdit", "NotebookEdit"):
                        fp = inp.get("file_path") or inp.get("notebook_path")
                        if not fp:
                            continue
                        fpn = os.path.normcase(os.path.abspath(fp))
                        if fpn not in hits:
                            continue
                        rec = hits[fpn].setdefault(sid_l, {"count": 0, "first": ts, "last": ts, "how": "hand-edit"})
                        rec["count"] += 1
                        if ts and (rec["first"] is None or ts < rec["first"]): rec["first"] = ts
                        if ts and (rec["last"]  is None or ts > rec["last"]):  rec["last"]  = ts

                    elif name in ("Bash", "PowerShell"):
                        cmd = (inp.get("command") or "").lower()
                        # only the command that actually regenerates the api contract
                        if not any(k in cmd for k in ("api:types", "generate-api-types", "generate_api_types")):
                            continue
                        for tgt in targets:
                            base = os.path.basename(tgt).lower()
                            if base not in ("schema.d.ts", "queries.ts", "types.ts", "openapi.json"):
                                continue
                            rec = hits[tgt].setdefault(sid_l, {"count": 0, "first": ts, "last": ts, "how": "ran generator/formatter"})
                            rec["count"] += 1
                            rec["how"] = "ran generator/formatter"
                            if ts and (rec["first"] is None or ts < rec["first"]): rec["first"] = ts
                            if ts and (rec["last"]  is None or ts > rec["last"]):  rec["last"]  = ts

def local(ts):
    if not ts: return "?"
    try:
        dt = datetime.fromisoformat(ts.replace("Z", "+00:00")).astimezone()
        return dt.strftime("%Y-%m-%d %H:%M:%S")
    except Exception:
        return ts

for t in targets:
    rel = os.path.relpath(t)
    print(f"\n### {rel}")
    sessions = hits.get(t, {})
    if not sessions:
        print("  no session transcript in the last %gh recorded an edit here" % hours)
        print("  (edited outside Claude Code, by a subagent, or by an older session)")
        continue
    for sid, rec in sorted(sessions.items(), key=lambda kv: kv[1]["last"] or "", reverse=True):
        tag = " (THIS watcher session)" if sid == self_id else ""
        meta = sess_meta.get(sid, {})
        label = meta.get("first_user") or "(no prompt captured)"
        how = rec.get("how", "hand-edit")
        print(f"  session {sid}{tag}")
        print(f"    {how}: {rec['count']}x   first: {local(rec['first'])}   last: {local(rec['last'])}")
        print(f"    task:  {label}")
PY
