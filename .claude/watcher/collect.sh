#!/usr/bin/env bash
# Read-only signal collector for the watcher loop.
# Writes the full snapshot to .claude/watcher/snapshot.txt, then prints ONLY a
# compact digest to stdout (~15 lines) so the loop spends few tokens per tick.
# The loop reads the full snapshot from disk only when the digest is not GREEN.
# Mutates nothing outside .claude/watcher/; the only git write is `git fetch`
# (remote-tracking refs only).
set -uo pipefail
cd "$(git rev-parse --show-toplevel)" || exit 1

DIR=.claude/watcher
OUT="$DIR/snapshot.txt"
SINCE_MIN="${1:-15}"

{
echo "# watcher snapshot  $(date '+%Y-%m-%d %H:%M:%S')"
echo "branch: $(git branch --show-current)   head: $(git rev-parse --short HEAD)"
echo
echo "## conflict markers in tracked files"
git grep -nI -E '^(<{7}|={7}|>{7})( |$)' -- ':!.claude/watcher/' || echo "(none)"
echo
echo "## git status (porcelain)"
git status --porcelain=v1 || true
echo
echo "## diff stat (working tree vs HEAD)"
git -c core.safecrlf=false diff --stat HEAD 2>/dev/null || true
echo
echo "## divergence vs origin/dev"
git fetch origin dev -q || echo "(fetch failed)"
MERGE_STATE="n/a"
if git rev-parse --verify -q origin/dev >/dev/null; then
  read -r ahead behind < <(git rev-list --left-right --count HEAD...origin/dev)
  echo "local ahead: $ahead   behind: $behind"
  if [ "${behind:-0}" -gt 0 ]; then
    base=$(git merge-base HEAD origin/dev)
    if git merge-tree "$base" HEAD origin/dev 2>/dev/null | grep -qE '^(<{7}|={7}|>{7})'; then
      MERGE_STATE="CONFLICT"
      echo "### merging origin/dev would CONFLICT:"
      git merge-tree "$base" HEAD origin/dev 2>/dev/null | grep -E '^(\+\+\+|<{7}|>{7})' | head -40
    else
      MERGE_STATE="clean"
      echo "clean: origin/dev auto-merges."
    fi
    echo "### commits on origin/dev not local:"
    git log --oneline HEAD..origin/dev | head -20
  else
    MERGE_STATE="clean"
  fi
else
  ahead=0; behind=0
  echo "(no origin/dev ref)"
fi
echo
echo "## files modified in the last ${SINCE_MIN} min"
find . \
  \( -path './.git' -o -path '*/node_modules' -o -path '*/.next' \
     -o -path '*/__pycache__' -o -path '*/.venv' -o -path './.claude/watcher' \) -prune \
  -o -type f -mmin "-${SINCE_MIN}" ! -name '*.log' \
     -printf '%TY-%Tm-%Td %TH:%TM  %p\n' 2>/dev/null | sort || true
echo
echo "## changed python files"
git diff --name-only HEAD -- '*.py' 2>/dev/null
echo
echo "## changed frontend files"
git diff --name-only HEAD -- 'frontend/src/*' 2>/dev/null
echo
echo "## last 12 commits"
git log --oneline -12
} > "$OUT" 2>&1

# ---- derive compact digest ----------------------------------------------------
markers=$(git grep -lI -E '^(<{7}|={7}|>{7})( |$)' -- ':!.claude/watcher/' 2>/dev/null)
marker_n=$(printf '%s' "$markers" | grep -c . || true)

new_hash=$(git -c core.safecrlf=false diff HEAD 2>/dev/null | git hash-object --stdin)
prev_hash=$(cat "$DIR/last-diff-hash.txt" 2>/dev/null || echo "")
[ "$new_hash" = "$prev_hash" ] && changed="UNCHANGED" || changed="CHANGED"
printf '%s\n' "$new_hash" > "$DIR/last-diff-hash.txt"
printf '%s\n' "$prev_hash" > "$DIR/prev-diff-hash.txt"

# tracked files changed vs HEAD, and which were touched inside the window
mapfile -t tracked_changed < <(git diff --name-only HEAD 2>/dev/null)
window_files=$(find . \
  \( -path './.git' -o -path '*/node_modules' -o -path '*/.next' -o -path './.idea' \
     -o -path '*/__pycache__' -o -path '*/.venv' -o -path './.claude' \
     -o -path '*/.pytest_cache' -o -path '*/.ruff_cache' \) -prune \
  -o -type f -mmin "-${SINCE_MIN}" ! -name '*.log' -printf '%P\n' 2>/dev/null \
  | sed 's#\\#/#g' | grep -vE '\.(db|tsbuildinfo)$|openapi\.json$' | sort)
window_n=$(printf '%s' "$window_files" | grep -c . || true)

verdict="GREEN"
reason="no markers; origin/dev not diverged"
if [ "${marker_n:-0}" -gt 0 ]; then
  verdict="ESCALATE"; reason="conflict markers in $marker_n file(s)"
elif [ "$MERGE_STATE" = "CONFLICT" ]; then
  verdict="ESCALATE"; reason="pull from origin/dev would conflict (behind $behind)"
elif [ "$changed" = "CHANGED" ]; then
  verdict="NEEDS-REVIEW"; reason="working diff changed since last tick"
fi

{
echo "VERDICT: $verdict"
echo "REASON: $reason"
echo "TIME: $(date '+%Y-%m-%d %H:%M:%S')   HEAD: $(git rev-parse --short HEAD)"
echo "MARKERS: ${marker_n:-0}"
echo "DIVERGENCE: ahead ${ahead:-0} behind ${behind:-0}   MERGE: $MERGE_STATE"
echo "DIFF: $changed  (hash ${new_hash:0:12}, prev ${prev_hash:0:12})"
echo "WINDOW_EDITS(${SINCE_MIN}m): $window_n"
if [ "${window_n:-0}" -gt 0 ]; then printf '%s\n' "$window_files" | sed 's/^/  - /'; fi
echo "TRACKED_CHANGED: ${#tracked_changed[@]} files"
} | tee "$DIR/digest.txt"
