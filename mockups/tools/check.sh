#!/usr/bin/env bash
# Render mockup pages in headless Chrome: screenshot + console errors.
# Usage: tools/check.sh <out_dir> page.html[?query] [more pages...]
# Prints "OK <page>" or the console errors for each page. Exit 1 if any page has errors.
set -u
CHROME="${CHROME:-/c/Program Files/Google/Chrome/Application/chrome.exe}"
DIR="$(cd "$(dirname "$0")/.." && pwd -W 2>/dev/null || pwd)"
OUT="$1"; shift
mkdir -p "$OUT"
PROF="$OUT/.chrome-prof-$$"
status=0
for page in "$@"; do
  name="$(echo "$page" | tr '?=&/' '____')"
  url="file:///${DIR#/}/$page"
  log="$("$CHROME" --headless=new --disable-gpu --user-data-dir="$PROF" --window-size="${SIZE:-1440,1000}" \
    --virtual-time-budget=8000 --enable-logging=stderr --v=0 --screenshot="$OUT/$name.png" "$url" 2>&1)"
  errs="$(echo "$log" | grep -E 'CONSOLE|Uncaught|Alpine Expression Error|is not defined' | grep -viE 'tailwindcss/browser|should not be used in production|extensions' || true)"
  if [ -n "$errs" ]; then echo "ERRORS $page"; echo "$errs" | sed 's/^/  /'; status=1; else echo "OK $page -> $OUT/$name.png"; fi
done
rm -rf "$PROF"
exit $status
