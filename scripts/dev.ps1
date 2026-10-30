# Start, stop, restart or inspect this checkout's dev servers. The one way agents run the app.
#   powershell -NoProfile -ExecutionPolicy Bypass -File scripts/dev.ps1 <start|stop|restart|status> [backend|frontend]
# Ports come from this checkout's files: PORT in .env (backend) and FRONTEND_PORT in
# frontend/.env.local (default 3000). PIDs are kept in .dev/, so stop only ever touches the
# servers this checkout started, never another worktree's.
param(
    [ValidateSet('start', 'stop', 'restart', 'status')][string]$Action = 'status',
    [ValidateSet('both', 'backend', 'frontend')][string]$Target = 'both'
)
$ErrorActionPreference = 'Stop'
$repo = Split-Path $PSScriptRoot -Parent
Set-Location $repo
$state = Join-Path $repo '.dev'
New-Item -ItemType Directory -Force $state | Out-Null

function Read-Var($file, $name, $default) {
    if (Test-Path $file) {
        $line = Get-Content $file | Where-Object { $_ -match "^$name=" } | Select-Object -Last 1
        if ($line) { return ($line -split '=', 2)[1].Trim() }
    }
    return $default
}

$backendPort = [int](Read-Var '.env' 'PORT' '8000')
$frontendPort = [int](Read-Var 'frontend\.env.local' 'FRONTEND_PORT' '3000')
$apiOrigin = Read-Var 'frontend\.env.local' 'API_ORIGIN' ''
$servers = @{
    backend  = @{ Port = $backendPort; Url = "http://127.0.0.1:$backendPort/api/health" }
    frontend = @{ Port = $frontendPort; Url = "http://localhost:$frontendPort" }
}
$targets = if ($Target -eq 'both') { 'backend', 'frontend' } else { , $Target }

function Test-Up($url) {
    try { (Invoke-WebRequest -UseBasicParsing $url -TimeoutSec 3).StatusCode -lt 500 } catch { $false }
}

function Get-SavedPid($name) {
    $file = Join-Path $state "$name.pid"
    if (-not (Test-Path $file)) { return $null }
    $id = [int](Get-Content $file)
    if (Get-Process -Id $id -ErrorAction SilentlyContinue) { return $id }
    Remove-Item $file
    return $null
}

function Stop-Server($name) {
    $id = Get-SavedPid $name
    if ($id) {
        # /T takes the reloader's and pnpm's child processes with it.
        taskkill /PID $id /T /F | Out-Null
        Remove-Item (Join-Path $state "$name.pid")
        Write-Host "$name stopped (PID $id)"
    } else {
        Write-Host "${name}: not started by this checkout"
    }
    $port = $servers[$name].Port
    $holder = Get-NetTCPConnection -State Listen -LocalPort $port -ErrorAction SilentlyContinue
    if ($holder) {
        Write-Host "  port $port is still held by PID $($holder.OwningProcess -join ',') (not ours; left alone)"
    }
}

function Start-Server($name) {
    $port = $servers[$name].Port
    if (Get-SavedPid $name) { Write-Host "$name already running; use restart"; return }
    if (Get-NetTCPConnection -State Listen -LocalPort $port -ErrorAction SilentlyContinue) {
        throw "$name port $port is taken by another process. Pick a free port in .env / frontend\.env.local; do not kill it."
    }
    $out = Join-Path $state "$name.out.log"
    $err = Join-Path $state "$name.err.log"
    # Launched through WMI so the server inherits none of this shell's handles: with Start-Process
    # -Redirect* it would hold the caller's output pipe open and the agent's tool call never returns.
    # The cmd wrapper does the log redirection and stays the parent, so taskkill /T reaches the tree.
    # SSLKEYLOGFILE (Avast) makes real LLM/embedder clients fail with PermissionError.
    if ($name -eq 'backend') {
        $dir = $repo
        $cmd = "cmd.exe /c set SSLKEYLOGFILE=& `"$repo\.venv\Scripts\python.exe`" -m app > `"$out`" 2> `"$err`""
    } else {
        $dir = Join-Path $repo 'frontend'
        $cmd = "cmd.exe /c pnpm dev -p $port > `"$out`" 2> `"$err`""
    }
    $created = Invoke-CimMethod Win32_Process -MethodName Create -Arguments @{ CommandLine = $cmd; CurrentDirectory = $dir }
    if ($created.ReturnValue -ne 0) { throw "could not launch $name (Win32 error $($created.ReturnValue))" }
    $p = Get-Process -Id $created.ProcessId
    Set-Content (Join-Path $state "$name.pid") $p.Id
    $limit = if ($name -eq 'backend') { 60 } else { 120 }
    for ($i = 0; $i -lt $limit; $i++) {
        if (Test-Up $servers[$name].Url) { Write-Host "$name up (PID $($p.Id)): $($servers[$name].Url)"; return }
        if ($p.HasExited) { break }
        Start-Sleep 1
    }
    Write-Host "$name did NOT come up. Last lines of $err :"
    Get-Content $err -Tail 20 -ErrorAction SilentlyContinue
    exit 1
}

foreach ($name in $targets) {
    switch ($Action) {
        'stop' { Stop-Server $name }
        'start' { Start-Server $name }
        'restart' { Stop-Server $name; Start-Server $name }
        'status' {
            $id = Get-SavedPid $name
            $up = if (Test-Up $servers[$name].Url) { 'UP' } else { 'DOWN' }
            Write-Host ("{0,-8} {1,-4} port {2}  pid {3}  {4}" -f $name, $up, $servers[$name].Port, $(if ($id) { $id } else { '-' }), $servers[$name].Url)
        }
    }
}
if ($Action -ne 'stop' -and $apiOrigin -and $apiOrigin -notmatch ":$backendPort$") {
    Write-Host "WARNING: frontend\.env.local API_ORIGIN=$apiOrigin does not match backend port $backendPort"
}
Write-Host "Logs: $state\<backend|frontend>.<out|err>.log   Dev login: dev@local.test / devpassword123"
