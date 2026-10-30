# Prepare a new Orca worktree so its backend + frontend run beside the main checkout.
# Orca runs this from orca.yaml with ORCA_ROOT_PATH (main checkout) and ORCA_WORKTREE_PATH set.
# Safe to re-run: existing .env, data/ and node_modules are left alone.
$ErrorActionPreference = 'Stop'

$root = if ($env:ORCA_ROOT_PATH) { $env:ORCA_ROOT_PATH } else { 'D:\FInalAdaptiveTrainer' }
$wt = if ($env:ORCA_WORKTREE_PATH) { $env:ORCA_WORKTREE_PATH } else { (Get-Location).Path }
Set-Location $wt

# Stable per-worktree ports derived from the folder name, so worktrees never collide
# with each other or with the main checkout (8000/8099, 3000).
$name = Split-Path $wt -Leaf
$hash = 0
foreach ($c in $name.ToCharArray()) { $hash = ($hash * 31 + [int]$c) % 600 }
$backendPort = 8200 + $hash
$frontendPort = 3100 + $hash

# Python: an own venv per worktree. A junction to a shared venv breaks every worktree as soon
# as one of them installs a dependency while another backend holds its files open.
if (-not (Test-Path .venv\Scripts\python.exe)) {
    uv venv --python 3.12 .venv
}
uv pip install --python .venv\Scripts\python.exe -e ".[dev]" --override scripts\uv-overrides.txt
if ($LASTEXITCODE -ne 0) { throw "uv pip install failed" }

# Backend config: main .env with this worktree's port.
if (-not (Test-Path .env)) {
    (Get-Content "$root\.env") -replace '^PORT=.*', "PORT=$backendPort" | Set-Content .env -Encoding utf8
}

# Own copy of the dev DB and uploaded books; book delete unlinks files, so never share data/.
if (-not (Test-Path data\adaptive_trainer.db)) {
    New-Item -ItemType Directory -Force data | Out-Null
    Copy-Item "$root\data\adaptive_trainer.db" data\
    if (Test-Path "$root\data\books") { Copy-Item "$root\data\books" data\ -Recurse }
}
.\.venv\Scripts\python.exe -m alembic upgrade head

# Frontend: real node_modules (Turbopack rejects a junctioned one), pointed at this backend.
if (-not (Test-Path frontend\.env.local)) {
    $lines = (Get-Content "$root\frontend\.env.local") -replace '^API_ORIGIN=.*', "API_ORIGIN=http://127.0.0.1:$backendPort" |
        Where-Object { $_ -notmatch '^FRONTEND_PORT=' }
    $lines + "FRONTEND_PORT=$frontendPort" | Set-Content frontend\.env.local -Encoding utf8
}
Push-Location frontend
pnpm install --frozen-lockfile --prefer-offline
Pop-Location

Write-Host ""
Write-Host "Worktree '$name' ready."
Write-Host "  Run it  : powershell -NoProfile -ExecutionPolicy Bypass -File scripts/dev.ps1 start"
Write-Host "  Backend : http://127.0.0.1:$backendPort   Frontend: http://localhost:$frontendPort"
