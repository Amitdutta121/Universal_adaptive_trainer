# Piston sandbox

The code-execution sandbox behind `graders.executors.piston.PistonExecutor`.
[Piston](https://github.com/engineer-man/piston) (MIT) is an HTTP API that runs each job in an
[Isolate](https://github.com/ioi/isolate) box. Image: `ghcr.io/engineer-man/piston` (API 3.1.1),
pinned by digest in `docker-compose.yml`. Runtime used by the executor: **python 3.12.0**.

## Start

```powershell
docker compose -f docker/piston/docker-compose.yml up -d
```

Needs a Docker host on **cgroup v2** (Docker Desktop's WSL 2 backend and current Linux distros are).
The entrypoint exits with "Please make sure your system is using cgroup v2" otherwise.

## Install the python runtime (once; it lives in the `piston_packages` volume)

```powershell
curl.exe -X POST -H "Content-Type: application/json" `
  -d '{\"language\":\"python\",\"version\":\"3.12.0\"}' http://127.0.0.1:2000/api/v2/packages
```

or from bash: `curl -X POST -H 'Content-Type: application/json' -d '{"language":"python","version":"3.12.0"}' http://127.0.0.1:2000/api/v2/packages`.
`GET /api/v2/packages` lists what can be installed. Takes ~30 s (downloads from the Piston
GitHub releases); after that the container needs no internet.

## Health check

```powershell
curl.exe http://127.0.0.1:2000/api/v2/runtimes
# [{"language":"python","version":"3.12.0","aliases":["py","py3","python3","python3.12"]}]
.\.venv\Scripts\python.exe -m pytest tests/graders/test_piston.py -q   # skipped when Piston is down
```

`PISTON_URL` points the tests elsewhere (default `http://127.0.0.1:2000`).

## Limits

Server-side caps are set in `docker-compose.yml` (`PISTON_*`); a request may ask for less, never
more. `PistonExecutor` sends per run: `run_timeout` = `run_cpu_time` = `RunRequest.timeout_s`
(max 30 s) and `run_memory_limit` = 256 MiB. Per job: 64 processes, 256 open files, 10 MB per
written file, 64 KiB of stdout and of stderr, no network. The container itself is capped at
2 CPUs / 2 GiB, 16 concurrent jobs.

What the API reports (and how the executor maps it):

| event | `run` in the response | `RunResult` |
|---|---|---|
| timeout (wall or CPU) | `status "TO"`, `signal "SIGKILL"`, `code null` | `timed_out=True`, `exit_code=None` |
| memory limit | `status "RE"`, `code 137`, `memory` ≈ limit, stderr `... Killed  python3.12 "$@"` | `exit_code=None`, stderr + `MemoryError: killed, ... memory limit` |
| output over 64 KiB | `status "OL"`/`"EL"`, `signal "SIGKILL"` | `exit_code=None`, stderr + `killed: stdout exceeded ...` |
| normal exit | `code n`, `status null` or `"RE"` | `exit_code=n` |

## Security notes

- **Privileged container.** Piston requires `privileged: true`: its entrypoint creates a cgroup
  v2 subtree under `/sys/fs/cgroup`, and Isolate creates mount/PID/network/IPC namespaces and a
  cgroup per job. A privileged container is effectively root on the Docker host (in the Docker
  Desktop case, the WSL 2 VM) if the Piston API process itself is compromised — so the trust
  boundary is Isolate, not Docker.
- **Localhost only.** The API has no authentication and runs any code it is sent, so the port is
  bound to `127.0.0.1:2000`. Never publish it on `0.0.0.0` or put it behind a public proxy; in a
  deployment, put it on a private Docker network reachable only by the app.
- **Why it is still far safer than `LocalExecutor`.** `LocalExecutor` runs submitted code as your
  user, with your files, network and processes. In Piston every job runs as a throwaway uid in a
  fresh box: only its own directory is writable (`/etc`, `/usr`, the runtimes are read-only;
  `/tmp` is per-job), no network (not even the Piston API on loopback), its own PID namespace
  (no `/proc/1`, no host processes), a 64-process cap (fork bombs stall, they do not spread), a
  cgroup memory cap and a wall/CPU clock. `tests/graders/test_piston.py` checks each of these.
- **Not contained by the sandbox:** CPU and memory pressure on the Docker host up to the
  container's caps; a kernel exploit from inside a box (Isolate shares the host kernel — use
  gVisor/Firecracker if that is in your threat model); and the runtime download, which trusts
  Piston's GitHub release index.
