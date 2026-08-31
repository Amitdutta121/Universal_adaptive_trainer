# Instructor Studio (Next.js)

The React frontend for the FastAPI JSON API. See `docs/DECISIONS.md` ADR-043
for why it exists and what it is not allowed to do.

The rule that matters: **this app holds no business logic.** Scoring, taxonomy validation, the
judge gate and the adaptive engine live in `app/`. Anything this UI needs that the API does not
expose is added to `app/web/routes/api/` first.

## Running it

The backend must be running first — this app has no data of its own.

```powershell
# terminal 1, from the repository root
.\.venv\Scripts\python.exe -m app

# terminal 2
cd frontend
pnpm install
pnpm run dev            # http://localhost:3000
```

The browser requests `/api/*` on `localhost:3000` and `next.config.ts` forwards it to FastAPI, so
there is no CORS in development and the backend URL never reaches the client bundle. Point it
elsewhere with `API_ORIGIN` in `.env.local` (see `.env.example`).

## Types come from the backend

`src/lib/api/schema.d.ts` is compiled from the FastAPI application's own OpenAPI document. Do not
edit it, and do not hand-write an interface for a response the backend already models.

```powershell
pnpm run api:types      # re-reads app.main:create_app() and recompiles the types
```

Run it whenever a Pydantic schema under `app/web/routes/api/` changes. A renamed field then shows
up as a failed typecheck rather than a blank column. The compiled types are committed so a build
needs no Python; the intermediate `openapi.json` is not.

## Checks

```powershell
pnpm run check          # typecheck + lint + tests
pnpm run build          # production build (also typechecks)
```

`pnpm run lint` is Biome, configured to 100 columns to match ruff on the Python side.

## Layout

```
src/
  app/                    Routes. One directory per professor section.
    page.tsx              Dashboard — a server component, fetched at request time.
    questions/            The worked example of the interactive pattern.
      page.tsx            Server shell: the Suspense boundary the URL state needs.
      questions-browser.tsx   Client: URL filters, query, table.
      [question_id]/      Server component with async params (Next 16).
      generate/           The spec sheet: one row per book chunk, three difficulty
                          columns, formats per row. The worked example of a feature
                          split into files — types, hooks, and one component each.
    books/                Import a document, then manage what it produced.
    curriculum/           The same shape for the taxonomy: index, version, subtopic.
  components/
    providers.tsx         Query client, URL-state adapter, tooltips.
    app-sidebar.tsx       Navigation, driven by lib/navigation.ts.
    query-state.tsx       Loading, error, empty and not-built-yet states.
    collapsible-panel.tsx Reference material that stays shut until it is asked for.
    copy-button.tsx       Copy to clipboard, reporting a failure rather than swallowing it.
  lib/
    api/client.ts         The only place that talks to the API.
    api/queries.ts        Query keys and hooks. All server state lives here.
    api/schema.d.ts       Generated. Do not edit.
    display.ts            Timestamps, counts and machine codes, formatted one way.
    json-document.ts      The upload checks that need no knowledge of a contract.
    navigation.ts         Frontend navigation metadata for the dashboard and sidebar.
```

## Conventions

- **Server state belongs to TanStack Query**, in `lib/api/queries.ts`. React state is for what the
  browser owns — an open dialog, an unsaved form, a code buffer being typed.
- **Filters and pagination belong in the URL** (`nuqs`), so a professor can share or reload a view.
  A component that reads them needs a `<Suspense>` boundary above it.
- **A screen with no implementation says so.** Do not render an empty table for a section that was
  never built; it reads as "there is nothing here". Use `NotBuiltYet`.
- **Never claim a judge passed when it did not answer.** An absent measurement is shown as absent,
  which is the same rule the backend follows.
- `src/components/ui/` is shadcn/ui output. It is ours to edit, but it is excluded from linting so
  a component can be re-fetched without a diff war.
- **A screen never re-derives a backend rule to decide what to offer.** The curriculum delete is the
  worked example: two of its refusals have no override, and the dialog knows which by reading the
  error code the API sent (`conflict_not_overridable`), not by reimplementing the rule.
- **Shared by two features means a shared module.** `lib/display.ts` and `lib/json-document.ts` hold
  what books and curriculum both need; what stays in a feature folder is the wording that carries
  meaning there — `partial` for a book, `replaced` for a curriculum version.
