"use client";

/**
 * Model settings: which provider and model each role uses (Task 44).
 *
 * Instance-wide, so it lives outside any course: a Settings modal opened from My courses and
 * the sidebar (`SettingsDialog`), with `/settings` kept as a page for direct links. Both show
 * the same category nav: Providers (keys and the default), then the roles grouped by what they do,
 * then Appearance. Every signed-in professor can see what is
 * configured (keys masked); only an admin can change it. A value saved here overrides
 * `.env`; an empty field keeps `.env`'s. Save is enabled only by a passing Test of exactly
 * the values in the form: the backend refuses a save without that test's token anyway.
 *
 * A new embedding model is not active when saved: every book chunk is re-embedded first,
 * and retrieval keeps using the old model until that finishes.
 *
 * The default provider (ADR-068) is what every role without a provider of its own calls; a
 * role can pick any set-up provider and one of its models. Keys and endpoints belong to the
 * provider (the Providers pane), not the role.
 */

import {
  Bot,
  Library,
  Loader2,
  type LucideIcon,
  Moon,
  PenLine,
  Plug,
  RotateCcw,
  Sun,
  SunMoon,
  XCircle,
} from "lucide-react";
import { useTheme } from "next-themes";
import { useId, useState } from "react";
import { PageHeader } from "@/components/page-header";
import { QueryError, TableSkeleton } from "@/components/query-state";
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Progress } from "@/components/ui/progress";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { readApiError } from "@/lib/api/client";
import {
  useModelSettings,
  useResetRoleSettings,
  useSaveRoleSettings,
  useTestRoleSettings,
} from "@/lib/api/queries";
import type { Schemas } from "@/lib/api/types";
import { ModelPicker } from "./model-picker";
import { ProvidersPane } from "./providers-pane";

type RoleSettings = Schemas["RoleSettingsResponse"];
type ModelRole = Schemas["ModelRole"];
type TestResult = Schemas["SettingsTestResponse"];
type Provider = Schemas["ProviderOut"];
type Settings = Schemas["ModelSettingsResponse"];

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

/** The form's values, as the API takes them: empty means the default provider, or its model. */
interface Draft {
  provider: string;
  model: string;
}

function draftBody(draft: Draft): Schemas["RoleSettingsUpdate"] {
  return {
    provider: draft.provider || null,
    model: draft.model || null,
    // The endpoint and key come from the provider; drop any a role stored before ADR-068.
    base_url: null,
    api_key: null,
    clear_api_key: true,
  };
}

/** The values a role starts from: saved ones, and empty for anything that comes from .env. */
function baseline(role: RoleSettings): Draft {
  return {
    provider: role.sources.provider === "db" ? role.provider : "",
    model: role.sources.model === "db" ? role.model : "",
  };
}

/** The provider a role follows when it picks none; embeddings fall back to OpenRouter's. */
function defaultProviderFor(role: ModelRole, settings: Settings): Provider | undefined {
  const route = settings.providers.find((provider) => provider.id === settings.route);
  const id = role === "embeddings" && !route?.embedding_model ? "openrouter" : settings.route;
  return settings.providers.find((provider) => provider.id === id);
}

function RoleRow({ role, settings }: { role: RoleSettings; settings: Settings }) {
  const id = useId();
  const canEdit = settings.can_edit;
  const meta = ROLES[role.role];
  const embeddings = role.role === "embeddings";
  const start = baseline(role);
  const [draft, setDraft] = useState<Draft>(start);
  const [failure, setFailure] = useState<{ draft: Draft; result: TestResult } | null>(null);
  const test = useTestRoleSettings();
  const save = useSaveRoleSettings();
  const reset = useResetRoleSettings();

  const fallback = defaultProviderFor(role.role, settings);
  const providerId = draft.provider || fallback?.id || role.provider;
  const provider = settings.providers.find((item) => item.id === providerId);
  const providerChanged = draft.provider !== start.provider;
  // A new provider without a chosen model runs on that provider's default one.
  const providerModel = (embeddings ? provider?.embedding_model : provider?.chat_model) ?? "";
  const implicitModel = providerChanged
    ? providerModel
    : role.sources.model === "env"
      ? role.model
      : "";
  const shownModel = draft.model || (providerChanged ? providerModel : role.model);
  const choices = settings.providers.filter(
    (item) => item.id === draft.provider || (item.configured && (!embeddings || item.embeds)),
  );

  const saved = Object.values(role.sources).includes("db");
  const switching = role.switch?.status === "queued" || role.switch?.status === "running";
  const editable = canEdit && role.testable && !switching;
  const changed = JSON.stringify(draft) !== JSON.stringify(start);
  const busy = test.isPending || save.isPending;
  // A failed test is shown only while the form still holds the values it tested.
  const failed = failure && JSON.stringify(failure.draft) === JSON.stringify(draft) ? failure : null;
  const error = readApiError(test.error ?? save.error);

  const chooseProvider = (value: string) =>
    setDraft({ provider: value === "default" ? "" : value, model: "" });
  // Picking the model the role would use anyway is no change.
  const chooseModel = (model: string) =>
    setDraft({ ...draft, model: model === implicitModel ? "" : model });
  const discard = () => {
    setDraft(start);
    setFailure(null);
  };
  // Save needs a passing test of exactly these values; the backend refuses it otherwise.
  const testAndSave = async () => {
    const tested = draft;
    const result = await test.mutateAsync({ role: role.role, body: draftBody(tested) });
    if (!result.ok || !result.test_token) {
      setFailure({ draft: tested, result });
      return;
    }
    await save.mutateAsync({
      role: role.role,
      body: { ...draftBody(tested), test_token: result.test_token },
    });
    setFailure(null);
  };
  const disabledReason = switching
    ? "Wait for the current switch to finish"
    : "Can be set once lecture upload exists";

  return (
    <section className="space-y-3 border-b py-5 first:pt-0 last:border-b-0 last:pb-0">
      <div className="flex flex-wrap items-start gap-x-6 gap-y-3">
        <div className="min-w-0 flex-1 basis-56">
          <h3 className="flex items-center gap-2 font-medium">
            {meta.label}
            {meta.inUse ? null : <Badge variant="outline">Not used yet</Badge>}
            {role.configured ? null : <Badge variant="destructive">No key</Badge>}
          </h3>
          <p className="text-muted-foreground text-sm">{meta.purpose}</p>
        </div>
        <div className="w-full space-y-1.5 sm:w-[30rem]">
          {canEdit ? (
            <div className="grid gap-2 sm:grid-cols-[11rem_1fr]">
              <Select
                value={draft.provider || "default"}
                disabled={!editable || busy}
                onValueChange={chooseProvider}
              >
                <SelectTrigger
                  id={`${id}-provider`}
                  aria-label="Provider"
                  className="h-auto w-full py-1.5"
                  title={editable ? undefined : disabledReason}
                >
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="default">
                    Default ({fallback?.label ?? role.provider})
                  </SelectItem>
                  {choices.map((item) => (
                    <SelectItem key={item.id} value={item.id}>
                      {item.label}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
              <ModelPicker
                value={shownModel}
                provider={providerId as Provider["id"]}
                listed={Boolean(provider?.lists_models && provider.configured)}
                embeddings={embeddings}
                disabled={!editable || busy}
                disabledReason={disabledReason}
                onSelect={chooseModel}
              />
            </div>
          ) : (
            <p className="truncate rounded-md border px-3 py-2 font-mono text-sm">
              {provider?.label ?? role.provider} · {role.model}
            </p>
          )}
          <div className="flex items-center gap-2 text-muted-foreground text-xs">
            <span>{saved ? "Saved for this instance" : "From .env"}</span>
            {canEdit && saved && !changed ? (
              <button
                type="button"
                className="inline-flex items-center gap-1 underline-offset-2 hover:text-foreground hover:underline disabled:opacity-50"
                disabled={reset.isPending || switching}
                onClick={() => reset.mutate(role.role)}
              >
                <RotateCcw className="size-3" />
                Use .env
              </button>
            ) : null}
          </div>
        </div>
      </div>

      {changed ? (
        <div className="flex flex-wrap items-center gap-2 rounded-md border bg-muted/40 px-3 py-2">
          <p className="min-w-0 flex-1 text-sm">
            Switch to {providerChanged ? `${provider?.label ?? providerId} · ` : null}
            <span className="font-mono">{shownModel || "its default model"}</span>
            <span className="text-muted-foreground">
              {" "}
              · tested with one short call before it is saved
              {embeddings ? "; every chunk is re-embedded first" : ""}
            </span>
          </p>
          <Button variant="ghost" size="sm" disabled={busy} onClick={discard}>
            Discard
          </Button>
          <Button size="sm" disabled={busy} onClick={() => void testAndSave()}>
            {test.isPending ? (
              <>
                <Loader2 className="animate-spin" />
                Testing…
              </>
            ) : save.isPending ? (
              <>
                <Loader2 className="animate-spin" />
                Saving…
              </>
            ) : failed ? (
              "Test again"
            ) : (
              "Test and save"
            )}
          </Button>
        </div>
      ) : null}
      {failed ? (
        <Alert variant="destructive">
          <XCircle />
          <AlertTitle>Test failed, nothing was saved</AlertTitle>
          <AlertDescription>{failed.result.error}</AlertDescription>
        </Alert>
      ) : null}
      {error ? (
        <Alert variant="destructive">
          <XCircle />
          <AlertTitle>{error.message}</AlertTitle>
          {error.detail ? <AlertDescription>{error.detail}</AlertDescription> : null}
        </Alert>
      ) : null}

      {embeddings ? <SwitchProgress role={role} /> : null}
    </section>
  );
}

type CategoryId = "providers" | "authoring" | "content" | "assistants" | "appearance";

/** The settings nav: a few standard groups, each listing only settings that exist today. */
const CATEGORIES: {
  id: CategoryId;
  label: string;
  icon: LucideIcon;
  summary: string;
  roles?: ModelRole[];
}[] = [
  {
    id: "providers",
    label: "Providers",
    icon: Plug,
    summary:
      "The AI providers the app can call, and the default every role uses unless it picks another.",
  },
  {
    id: "authoring",
    label: "Question authoring",
    icon: PenLine,
    summary: "The models that write questions and judge them before review.",
    roles: ["generation", "judges"],
  },
  {
    id: "content",
    label: "Content & retrieval",
    icon: Library,
    summary: "How course material is turned into text and searched for the passages a question uses.",
    roles: ["embeddings", "transcription"],
  },
  {
    id: "assistants",
    label: "Assistants",
    icon: Bot,
    summary: "The models behind the professor agent and the help students see.",
    roles: ["agent", "tutorials", "ask_why"],
  },
  {
    id: "appearance",
    label: "Appearance",
    icon: SunMoon,
    summary: "How the app looks on this browser.",
  },
];

const THEMES = [
  { value: "light", label: "Light", icon: Sun },
  { value: "dark", label: "Dark", icon: Moon },
  { value: "system", label: "System", icon: SunMoon },
] as const;

function AppearancePane() {
  const { theme, setTheme } = useTheme();
  const active = theme ?? "system";
  return (
    <section className="space-y-3">
      <div>
        <h3 className="font-medium">Theme</h3>
        <p className="text-muted-foreground text-sm">
          System follows your operating system. Saved in this browser only.
        </p>
      </div>
      <fieldset className="flex w-fit rounded-md border p-0.5" aria-label="Theme">
        {THEMES.map(({ value, label, icon: Icon }) => (
          <Button
            key={value}
            size="sm"
            variant={active === value ? "secondary" : "ghost"}
            aria-pressed={active === value}
            onClick={() => setTheme(value)}
          >
            <Icon />
            {label}
          </Button>
        ))}
      </fieldset>
    </section>
  );
}

/** One category's model settings: the admin notice, then its providers or its roles. */
function ModelPane({ category }: { category: (typeof CATEGORIES)[number] }) {
  const settings = useModelSettings();
  if (settings.isPending) return <TableSkeleton rows={3} />;
  if (settings.isError) return <QueryError error={settings.error} />;
  const data = settings.data;

  return (
    <div className="space-y-5">
      {data.can_edit ? null : (
        <Alert>
          <AlertTitle>Only an admin can change these</AlertTitle>
          <AlertDescription>
            You can see what is configured. Ask an admin to change a model or key.
          </AlertDescription>
        </Alert>
      )}
      {category.roles ? (
        <div>
          {category.roles.map((name) => {
            const role = data.roles.find((item) => item.role === name);
            return role ? (
              <RoleRow key={name} role={role} settings={data} />
            ) : null;
          })}
        </div>
      ) : (
        <ProvidersPane settings={data} />
      )}
    </div>
  );
}

/** Category nav on the left, the chosen category's settings on the right. */
function SettingsLayout() {
  return (
    <Tabs
      orientation="vertical"
      defaultValue={CATEGORIES[0].id}
      className="min-h-0 flex-1 gap-0 md:flex-row"
    >
      <TabsList
        variant="line"
        aria-label="Settings categories"
        className="w-full shrink-0 items-stretch justify-start gap-0.5 border-b p-2 md:h-auto! md:w-56 md:self-stretch md:border-r md:border-b-0 md:bg-muted/30"
      >
        {CATEGORIES.map(({ id, label, icon: Icon }) => (
          <TabsTrigger
            key={id}
            value={id}
            className="h-9 flex-none justify-start px-2.5 font-normal after:hidden data-active:bg-muted data-active:font-medium"
          >
            <Icon />
            {label}
          </TabsTrigger>
        ))}
      </TabsList>
      {CATEGORIES.map((category) => (
        <TabsContent key={category.id} value={category.id} className="min-h-0 overflow-y-auto p-6">
          <div className="mb-5 space-y-1">
            <h2 className="font-semibold text-base">{category.label}</h2>
            <p className="text-muted-foreground text-sm">{category.summary}</p>
          </div>
          {category.id === "appearance" ? <AppearancePane /> : <ModelPane category={category} />}
        </TabsContent>
      ))}
    </Tabs>
  );
}

/** Settings in a modal, opened from My courses and the sidebar without leaving the page. */
export function SettingsDialog({
  open,
  onOpenChange,
}: {
  open: boolean;
  onOpenChange: (open: boolean) => void;
}) {
  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="flex h-[min(88vh,46rem)] flex-col gap-0 p-0 sm:max-w-5xl">
        <DialogHeader className="border-b px-6 py-4">
          <DialogTitle>Settings</DialogTitle>
          <DialogDescription className="sr-only">
            App settings, grouped by category.
          </DialogDescription>
        </DialogHeader>
        <SettingsLayout />
      </DialogContent>
    </Dialog>
  );
}

export function SettingsScreen() {
  return (
    <>
      <PageHeader
        title="Settings"
        summary="Models, providers and appearance for this instance."
        showTaxonomySelector={false}
      />
      <Card className="min-h-[36rem] gap-0 py-0">
        <SettingsLayout />
      </Card>
    </>
  );
}
