"use client";

/**
 * Model settings: which provider and model each role uses (Task 44).
 *
 * Instance-wide, so it lives outside any course. Every signed-in professor can see what is
 * configured (keys masked); only an admin can change it. A value saved here overrides
 * `.env`; an empty field keeps `.env`'s. Save is enabled only by a passing Test of exactly
 * the values in the form: the backend refuses a save without that test's token anyway.
 *
 * A new embedding model is not active when saved: every book chunk is re-embedded first,
 * and retrieval keeps using the old model until that finishes.
 *
 * The route toggle above the roles points every role that has no saved settings of its own
 * at OpenRouter or Azure, both configured in `.env`; it needs no Test.
 */

import { CheckCircle2, Pencil, RotateCcw, XCircle } from "lucide-react";
import { useId, useState } from "react";
import { PageHeader } from "@/components/page-header";
import { QueryError, TableSkeleton } from "@/components/query-state";
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Progress } from "@/components/ui/progress";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { readApiError } from "@/lib/api/client";
import {
  useModelSettings,
  useProviderModels,
  useResetRoleSettings,
  useSaveRoleSettings,
  useSetRoute,
  useTestRoleSettings,
} from "@/lib/api/queries";
import type { Schemas } from "@/lib/api/types";

type RoleSettings = Schemas["RoleSettingsResponse"];
type ModelRole = Schemas["ModelRole"];
type TestResult = Schemas["SettingsTestResponse"];
type Route = Schemas["RouteUpdate"]["route"];

const ROUTES: { value: Route; label: string }[] = [
  { value: "openrouter", label: "OpenRouter" },
  { value: "azure", label: "Azure" },
];

/** What each role is for, and whether anything uses it yet. */
const ROLES: Record<ModelRole, { label: string; purpose: string; inUse: boolean }> = {
  generation: {
    label: "Generation",
    purpose: "Writes questions, taxonomy drafts and learned guidelines.",
    inUse: true,
  },
  judges: { label: "Judges", purpose: "Scores generated questions.", inUse: true },
  embeddings: {
    label: "Embeddings",
    purpose: "Ranks book chunks for retrieval. A new model re-embeds every chunk first.",
    inUse: true,
  },
  agent: { label: "Professor agent", purpose: "The course-setup chat agent.", inUse: false },
  tutorials: { label: "Tutorials", purpose: "Writes tutorial blocks.", inUse: false },
  ask_why: { label: "Ask why", purpose: "Answers a student's “why?”.", inUse: false },
  transcription: {
    label: "Transcription",
    purpose: "Turns lecture audio into text.",
    inUse: false,
  },
};

const ROLE_ORDER: ModelRole[] = [
  "generation",
  "judges",
  "embeddings",
  "agent",
  "tutorials",
  "ask_why",
  "transcription",
];

function SourceBadge({ source }: { source: "db" | "env" }) {
  return source === "db" ? (
    <Badge variant="secondary">saved</Badge>
  ) : (
    <Badge variant="outline">.env</Badge>
  );
}

function Field({
  label,
  value,
  source,
}: {
  label: string;
  value: string | null;
  source: "db" | "env";
}) {
  return (
    <div className="min-w-0 space-y-1">
      <dt className="text-muted-foreground text-xs">{label}</dt>
      <dd className="flex min-w-0 items-center gap-2 text-sm">
        <span className="truncate font-mono" title={value ?? undefined}>
          {value ?? "—"}
        </span>
        <SourceBadge source={source} />
      </dd>
    </div>
  );
}

function SwitchProgress({ role }: { role: RoleSettings }) {
  const change = role.switch;
  if (!change) return null;
  const active = change.status === "queued" || change.status === "running";
  if (active) {
    const percent = change.total > 0 ? Math.round((change.done / change.total) * 100) : 0;
    return (
      <div className="space-y-1.5 rounded-md border p-3">
        <p className="text-sm">
          Switching to <span className="font-mono">{change.model}</span>: re-embedded {change.done}{" "}
          / {change.total} chunks. Retrieval uses <span className="font-mono">{role.model}</span>{" "}
          until this finishes.
        </p>
        <Progress value={percent} aria-label="Re-embedding progress" />
      </div>
    );
  }
  if (change.status === "failed" || change.status === "cancelled") {
    return (
      <Alert variant="destructive">
        <XCircle />
        <AlertTitle>
          The switch to <span className="font-mono">{change.model}</span>{" "}
          {change.status === "cancelled" ? "was cancelled" : "failed"}
        </AlertTitle>
        <AlertDescription>
          {change.error ?? "No reason was recorded."} Retrieval still uses{" "}
          <span className="font-mono">{role.model}</span>. Save again to retry; chunks already
          re-embedded are kept.
        </AlertDescription>
      </Alert>
    );
  }
  return null;
}

/** The form's values, as the API takes them: empty means "use .env". */
interface Draft {
  provider: string;
  model: string;
  base_url: string;
  api_key: string;
}

function draftBody(draft: Draft): Schemas["RoleSettingsUpdate"] {
  return {
    provider: draft.provider || null,
    model: draft.model || null,
    base_url: draft.base_url || null,
    api_key: draft.api_key || null,
    // Removing just the saved key is "Use .env" on the whole role.
    clear_api_key: false,
  };
}

function RoleEditor({
  role,
  providers,
  onDone,
}: {
  role: RoleSettings;
  providers: string[];
  onDone: () => void;
}) {
  const id = useId();
  // Start from what is saved; a field that comes from .env starts empty (keeps .env).
  const [draft, setDraft] = useState<Draft>({
    provider: role.sources.provider === "db" ? role.provider : "",
    model: role.sources.model === "db" ? role.model : "",
    base_url: role.sources.base_url === "db" ? (role.base_url ?? "") : "",
    api_key: "",
  });
  // A passing test is only good for the exact values it tested.
  const [tested, setTested] = useState<{ draft: Draft; result: TestResult } | null>(null);
  const test = useTestRoleSettings();
  const save = useSaveRoleSettings();
  const provider = draft.provider || role.provider;
  const models = useProviderModels(provider, provider === "openrouter");

  const current = tested && JSON.stringify(tested.draft) === JSON.stringify(draft) ? tested : null;
  const canSave = current?.result.ok === true && current.result.test_token;
  const set = (field: keyof Draft) => (value: string) => setDraft({ ...draft, [field]: value });

  const runTest = async () => {
    const result = await test.mutateAsync({ role: role.role, body: draftBody(draft) });
    setTested({ draft, result });
  };
  const runSave = async () => {
    if (!current?.result.test_token) return;
    await save.mutateAsync({
      role: role.role,
      body: { ...draftBody(draft), test_token: current.result.test_token },
    });
    onDone();
  };
  const error = readApiError(test.error ?? save.error);

  return (
    <div className="space-y-4 rounded-md border bg-muted/30 p-4">
      <div className="grid gap-4 sm:grid-cols-2">
        <div className="space-y-1.5">
          <Label htmlFor={`${id}-provider`}>Provider</Label>
          <Select
            value={draft.provider || "env"}
            onValueChange={(value) => set("provider")(value === "env" ? "" : value)}
          >
            <SelectTrigger id={`${id}-provider`} className="w-full">
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value="env">From .env ({role.provider})</SelectItem>
              {providers.map((name) => (
                <SelectItem key={name} value={name}>
                  {name}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
        </div>
        <div className="space-y-1.5">
          <Label htmlFor={`${id}-model`}>Model</Label>
          <Input
            id={`${id}-model`}
            list={`${id}-models`}
            value={draft.model}
            onChange={(event) => set("model")(event.target.value)}
            placeholder={`From .env: ${role.model}`}
            className="font-mono"
            autoComplete="off"
          />
          <datalist id={`${id}-models`}>
            {(models.data ?? []).map((model) => (
              <option key={model.id} value={model.id}>
                {model.name}
              </option>
            ))}
          </datalist>
        </div>
        <div className="space-y-1.5">
          <Label htmlFor={`${id}-base-url`}>Base URL</Label>
          <Input
            id={`${id}-base-url`}
            value={draft.base_url}
            onChange={(event) => set("base_url")(event.target.value)}
            placeholder="Provider default"
            className="font-mono"
            autoComplete="off"
          />
        </div>
        <div className="space-y-1.5">
          <Label htmlFor={`${id}-key`}>API key</Label>
          <Input
            id={`${id}-key`}
            type="password"
            value={draft.api_key}
            onChange={(event) => set("api_key")(event.target.value)}
            placeholder={
              role.api_key_masked
                ? `Keep ${role.api_key_masked} (${role.sources.api_key === "db" ? "saved" : ".env"})`
                : "No key yet"
            }
            autoComplete="new-password"
          />
        </div>
      </div>

      {current ? (
        current.result.ok ? (
          <p className="flex items-center gap-1.5 text-emerald-700 text-sm dark:text-emerald-400">
            <CheckCircle2 className="size-4" />
            Test passed
            {current.result.dimension ? ` · ${current.result.dimension}-dimension vectors` : ""}.
          </p>
        ) : (
          <Alert variant="destructive">
            <XCircle />
            <AlertTitle>Test failed</AlertTitle>
            <AlertDescription>{current.result.error}</AlertDescription>
          </Alert>
        )
      ) : null}
      {error ? (
        <Alert variant="destructive">
          <XCircle />
          <AlertTitle>{error.message}</AlertTitle>
          {error.detail ? <AlertDescription>{error.detail}</AlertDescription> : null}
        </Alert>
      ) : null}

      <div className="flex flex-wrap items-center gap-2">
        <Button
          variant="outline"
          size="sm"
          disabled={test.isPending}
          onClick={() => void runTest()}
        >
          {test.isPending ? "Testing…" : "Test"}
        </Button>
        <Button
          size="sm"
          disabled={!canSave || save.isPending}
          onClick={() => void runSave()}
          title={canSave ? undefined : "Test these values first"}
        >
          {save.isPending ? "Saving…" : "Save"}
        </Button>
        <Button variant="ghost" size="sm" onClick={onDone}>
          Cancel
        </Button>
        {role.role === "embeddings" ? (
          <p className="text-muted-foreground text-xs">
            Saving a different model re-embeds every chunk before it takes over.
          </p>
        ) : null}
      </div>
    </div>
  );
}

function RoleRow({
  role,
  canEdit,
  providers,
}: {
  role: RoleSettings;
  canEdit: boolean;
  providers: string[];
}) {
  const [editing, setEditing] = useState(false);
  const reset = useResetRoleSettings();
  const meta = ROLES[role.role];
  const saved = Object.values(role.sources).includes("db");
  const switching = role.switch?.status === "queued" || role.switch?.status === "running";

  return (
    <section className="space-y-3 border-b py-5 first:pt-0 last:border-b-0 last:pb-0">
      <div className="flex flex-wrap items-start gap-2">
        <div className="min-w-0">
          <h2 className="flex items-center gap-2 font-medium">
            {meta.label}
            {meta.inUse ? null : <Badge variant="outline">Not used yet</Badge>}
            {role.configured ? null : <Badge variant="destructive">No key</Badge>}
          </h2>
          <p className="text-muted-foreground text-sm">{meta.purpose}</p>
        </div>
        {canEdit && !editing ? (
          <div className="ml-auto flex gap-2">
            {saved ? (
              <Button
                variant="ghost"
                size="sm"
                disabled={reset.isPending || switching}
                onClick={() => reset.mutate(role.role)}
              >
                <RotateCcw />
                Use .env
              </Button>
            ) : null}
            <Button
              variant="outline"
              size="sm"
              disabled={!role.testable || switching}
              title={role.testable ? undefined : "Can be set once lecture upload exists"}
              onClick={() => setEditing(true)}
            >
              <Pencil />
              Edit
            </Button>
          </div>
        ) : null}
      </div>

      <dl className="grid gap-3 sm:grid-cols-4">
        <Field label="Provider" value={role.provider} source={role.sources.provider} />
        <Field label="Model" value={role.model} source={role.sources.model} />
        <Field label="Base URL" value={role.base_url} source={role.sources.base_url} />
        <Field label="API key" value={role.api_key_masked} source={role.sources.api_key} />
      </dl>

      {role.role === "embeddings" ? <SwitchProgress role={role} /> : null}
      {editing ? (
        <RoleEditor role={role} providers={providers} onDone={() => setEditing(false)} />
      ) : null}
    </section>
  );
}

function RouteToggle({ settings }: { settings: Schemas["ModelSettingsResponse"] }) {
  const setRoute = useSetRoute();
  const error = readApiError(setRoute.error);

  return (
    <section className="space-y-3 border-b pb-5">
      <div className="flex flex-wrap items-start gap-2">
        <div className="min-w-0">
          <h2 className="flex items-center gap-2 font-medium">
            Route
            <SourceBadge source={settings.route_source} />
          </h2>
          <p className="text-muted-foreground text-sm">
            Every role below without its own saved settings calls this endpoint. Both come from
            .env. Chunks are embedded again for the new route on their next search.
          </p>
        </div>
        <fieldset className="ml-auto flex rounded-md border p-0.5" aria-label="Route">
          {ROUTES.map(({ value, label }) => {
            const unconfigured = value === "azure" && !settings.azure_configured;
            return (
              <Button
                key={value}
                size="sm"
                variant={settings.route === value ? "secondary" : "ghost"}
                aria-pressed={settings.route === value}
                disabled={!settings.can_edit || setRoute.isPending || unconfigured}
                title={unconfigured ? "Set AZURE_BASE_URL and AZURE_API_KEY in .env" : undefined}
                onClick={() => {
                  if (settings.route !== value) setRoute.mutate(value);
                }}
              >
                {label}
              </Button>
            );
          })}
        </fieldset>
      </div>
      {error ? (
        <Alert variant="destructive">
          <XCircle />
          <AlertTitle>{error.message}</AlertTitle>
          {error.detail ? <AlertDescription>{error.detail}</AlertDescription> : null}
        </Alert>
      ) : null}
    </section>
  );
}

export function SettingsScreen() {
  const settings = useModelSettings();

  return (
    <>
      <PageHeader
        title="Model settings"
        summary="Which provider and model each part of the app uses. Saved values override .env for the whole instance."
        showTaxonomySelector={false}
      />
      {settings.isSuccess && !settings.data.can_edit ? (
        <Alert>
          <AlertTitle>Only an admin can change these</AlertTitle>
          <AlertDescription>
            You can see what is configured. Ask an admin to change a model or key.
          </AlertDescription>
        </Alert>
      ) : null}
      <Card>
        <CardContent>
          {settings.isPending ? <TableSkeleton rows={7} /> : null}
          {settings.isError ? <QueryError error={settings.error} /> : null}
          {settings.isSuccess ? <RouteToggle settings={settings.data} /> : null}
          {settings.isSuccess
            ? ROLE_ORDER.map((name) => {
                const role = settings.data.roles.find((item) => item.role === name);
                return role ? (
                  <RoleRow
                    key={name}
                    role={role}
                    canEdit={settings.data.can_edit}
                    providers={settings.data.providers}
                  />
                ) : null;
              })
            : null}
        </CardContent>
      </Card>
    </>
  );
}
