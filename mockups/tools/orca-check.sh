#!/usr/bin/env bash
# Verify mockup pages in Orca's built-in browser: one private tab per run,
# a PNG screenshot per page, and console errors. Safe to run concurrently.
# Usage: tools/orca-check.sh <out_dir> page.html[?query] [more pages...]
set -u
DIR="$(cd "$(dirname "$0")/.." && pwd -W 2>/dev/null || pwd)"
OUT="$1"; shift
mkdir -p "$OUT"
T() { timeout 40 orca "$@" --json 2>/dev/null; }
jget() { py -3 -c "import json,sys; d=json.load(sys.stdin); print(eval(sys.argv[1]))" "$1"; }
PAGE="$(T tab create --url "about:blank" | jget "d['result']['browserPageId']")"
[ -z "$PAGE" ] && { echo "Could not open an Orca tab (is Orca running?)"; exit 2; }
status=0
for page in "$@"; do
  name="$(echo "$page" | tr '?=&/' '____')"
  T goto --url "file:///${DIR#/}/$page" --page "$PAGE" >/dev/null
  sleep 3   # CDN scripts + Alpine; `orca wait` can hang on file:// pages
  # Orca's screenshot intermittently returns runtime_unavailable; retry a few times.
  for try in 1 2 3 4; do
    T screenshot --page "$PAGE" | py -3 -c "
import json,sys,base64
d=json.load(sys.stdin)
if not d.get('ok'): sys.exit(1)
open(sys.argv[1],'wb').write(base64.b64decode(d['result']['data']))" "$OUT/$name.png" 2>/dev/null && break
    sleep 2
    [ $try = 4 ] && echo "  (no screenshot for $page: Orca screenshot kept failing)"
  done
  errs="$(T console --limit 50 --page "$PAGE" | py -3 -c "
import json,sys
m=json.load(sys.stdin).get('result',{}).get('messages',[])
for x in m:
  t=str(x.get('text') or x.get('message') or x)
  lv=str(x.get('level') or x.get('type') or '')
  if ('error' in lv.lower() or 'Alpine' in t or 'Uncaught' in t) and 'tailwindcss' not in t: print(lv, t[:300])")"
  if [ -n "$errs" ]; then echo "ERRORS $page"; echo "$errs" | sed 's/^/  /'; status=1; else echo "OK $page -> $OUT/$name.png"; fi
done
idx="$(T tab list | py -3 -c "import json,sys; print(next((t['index'] for t in json.load(sys.stdin)['result']['tabs'] if t['browserPageId']=='$PAGE'),''))")"
[ -n "$idx" ] && T tab close --index "$idx" >/dev/null
exit $status
