---
name: serve
description: Use when Amit asks to run, start, stop, restart, force-restart, or bring up the app / dev server / frontend / backend in this repo or any of its worktrees, asks whether it is running, or asks for the local URL. Runs scripts/dev.ps1, which reads this checkout's own ports and only touches servers this checkout started.
---

Run the app through `scripts/dev.ps1` from the root of the checkout you are working in (the main
repo or an Orca/agent worktree). Do not start `python -m app` or `pnpm dev` by hand, do not assume
ports 8000/3000, and do not kill processes by port, name, or command line: other worktrees and peer
sessions run their own servers on this machine.

```
powershell -NoProfile -ExecutionPolicy Bypass -File scripts/dev.ps1 <action> [backend|frontend]
```

| Ask | action |
|---|---|
| run / start / bring up | `start` |
| restart / force-restart / pick up code changes | `restart` |
| stop / kill / shut down | `stop` |
| is it running / what's the URL | `status` |

Omit the target for both apps; pass `backend` or `frontend` when only one was named.

Where things come from:
- Ports: `PORT` in `.env` (backend), `FRONTEND_PORT` in `frontend/.env.local` (frontend, default
  3000). `API_ORIGIN` in `frontend/.env.local` must point at the backend port; the script warns if not.
- PIDs and logs: `.dev/` in the checkout (`backend.err.log` etc.).
- Missing `.venv`, `.env` or `node_modules` means the checkout was never set up: run
  `scripts/orca-setup.ps1` (needs `ORCA_ROOT_PATH` pointing at `D:\FInalAdaptiveTrainer` when run by hand).

When `start` fails:
- "port … is taken by another process": that is someone else's server. Change the port in `.env`
  or `frontend/.env.local` (keep `API_ORIGIN` in sync), then `start` again. Never kill the holder.
- "did NOT come up": read the printed stderr tail and report it; do not claim the app is up.
- `PermissionError` on LLM/embedder calls: `SSLKEYLOGFILE` (Avast); the script already clears it.

Report the script's output as-is: the URLs, PIDs, and the log folder. Dev login:
`dev@local.test` / `devpassword123`.
