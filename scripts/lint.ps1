# Lint + typecheck gate: ruff, then frontend tsc and biome lint. Runs every step and exits non-zero
# if any failed (biome format is skipped on purpose: it fails repo-wide on CRLF, see CLAUDE.md).
#   powershell -NoProfile -ExecutionPolicy Bypass -File scripts/lint.ps1
$repo = Split-Path $PSScriptRoot -Parent
$failed = @()

Set-Location $repo
& "$repo\.venv\Scripts\python.exe" -m ruff check .
if ($LASTEXITCODE) { $failed += 'ruff' }

Set-Location (Join-Path $repo 'frontend')
pnpm tsc --noEmit
if ($LASTEXITCODE) { $failed += 'tsc' }
pnpm biome lint src
if ($LASTEXITCODE) { $failed += 'biome lint' }

if ($failed) { Write-Host "FAILED: $($failed -join ', ')"; exit 1 }
Write-Host 'All checks passed'
