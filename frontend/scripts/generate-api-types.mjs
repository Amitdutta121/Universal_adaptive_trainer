/**
 * Regenerate `src/lib/api/schema.d.ts` from the FastAPI application's own OpenAPI
 * document.
 *
 * The backend is the single source of truth for every request and response shape
 * (Pydantic v2 models under `app/web/routes/api/schemas.py`). Rather than restate
 * those shapes in TypeScript by hand — where they would silently drift — we ask
 * the Python app for its schema and compile it.
 *
 * The app is imported in-process, not requested over HTTP, so this works with no
 * server running and is safe to put in CI.
 */

import { execFileSync } from "node:child_process";
import { existsSync, mkdirSync, writeFileSync } from "node:fs";
import { dirname, join, resolve } from "node:path";
import { fileURLToPath, pathToFileURL } from "node:url";
import openapiTS, { astToString } from "openapi-typescript";

const frontendDir = resolve(dirname(fileURLToPath(import.meta.url)), "..");
const repoRoot = resolve(frontendDir, "..");
const schemaJson = join(frontendDir, "openapi.json");
const schemaTypes = join(frontendDir, "src", "lib", "api", "schema.d.ts");

/** Prefer the project's own virtualenv; fall back to whatever `python` is on PATH. */
function findPython() {
  const candidates = [
    join(repoRoot, ".venv", "Scripts", "python.exe"), // Windows
    join(repoRoot, ".venv", "bin", "python"), // POSIX
  ];
  const found = candidates.find((candidate) => existsSync(candidate));
  if (found) return found;
  console.warn("! No .venv found at the repo root; falling back to `python` on PATH.");
  return process.platform === "win32" ? "python" : "python3";
}

const DUMP = `
import json, sys
from app.main import create_app
json.dump(create_app().openapi(), open(sys.argv[1], "w"), indent=2)
`;

const python = findPython();
console.log(`> ${python} -c '<dump openapi>' ${schemaJson}`);
execFileSync(python, ["-c", DUMP, schemaJson], { cwd: repoRoot, stdio: "inherit" });

// openapi-typescript is used as a library rather than a spawned CLI: `npx` resolution
// differs between PowerShell, cmd and Git Bash on Windows, and this needs to work in all
// three.
mkdirSync(dirname(schemaTypes), { recursive: true });
console.log(`> openapi-typescript -> ${schemaTypes}`);
const ast = await openapiTS(pathToFileURL(schemaJson));
writeFileSync(schemaTypes, astToString(ast), "utf8");

console.log("API types regenerated.");
