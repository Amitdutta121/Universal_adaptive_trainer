"use client";

/**
 * Providers (ADR-068): which AI providers the app can call, and which one is the default.
 *
 * Each provider's key (and URL, for Azure and custom endpoints) and default model come from
 * `.env` and can be saved here instead. Saving makes one short test call first; nothing is
 * stored when it fails. The default provider is what every role uses unless the role picks
 * its own on its own screen; embeddings stay on OpenRouter when the default has none.
 */

import { Loader2, RotateCcw, XCircle } from "lucide-react";
import { useId, useState } from "react";
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { readApiError } from "@/lib/api/client";
import { useResetProvider, useSaveProvider, useSetRoute } from "@/lib/api/queries";
import type { Schemas } from "@/lib/api/types";
import { ModelPicker } from "./model-picker";

type Provider = Schemas["ProviderOut"];
type Settings = Schemas["ModelSettingsResponse"];

const URL_PLACEHOLDER: Partial<Record<Provider["id"], string>> = {
  azure: "https://<resource>.services.ai.azure.com/openai/v1/",
  custom: "http://localhost:8000/v1",
};

function ErrorAlert({ error }: { error: unknown }) {
  const problem = readApiError(error);
  if (!problem) return null;
  return (
    <Alert variant="destructive">
      <XCircle />
      <AlertTitle>{problem.message}</AlertTitle>
      {problem.detail ? <AlertDescription>{problem.detail}</AlertDescription> : null}
    </Alert>
  );
}

function DefaultProvider({ settings }: { settings: Settings }) {
  const id = useId();
  const setRoute = useSetRoute();
  const current = settings.providers.find((provider) => provider.id === settings.route);

  return (
    <section className="space-y-3 border-b pb-5">
      <div className="flex flex-wrap items-start gap-x-6 gap-y-3">
        <div className="min-w-0 flex-1 basis-56">
          <h3 className="font-medium">
            <label htmlFor={id}>Default provider</label>
          </h3>
          <p className="text-muted-foreground text-sm">
            Every role uses it, with its default model, unless the role picks another provider.
          </p>
        </div>
        <div className="w-full sm:w-80">
          <Select
            value={settings.route}
            disabled={!settings.can_edit || setRoute.isPending}
            onValueChange={(value) => setRoute.mutate(value as Provider["id"])}
          >
            <SelectTrigger id={id} className="w-full">
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              {settings.providers.map((provider) => (
                <SelectItem
                  key={provider.id}
                  value={provider.id}
                  disabled={!provider.configured && provider.id !== "openrouter"}
                >
                  {provider.label}
                  {provider.configured ? "" : " (not set up)"}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
        </div>
      </div>
      {current && !current.embedding_model ? (
        <p className="text-muted-foreground text-xs">
          {current.label} has no embedding models, so retrieval keeps using OpenRouter's.
        </p>
      ) : null}
      <ErrorAlert error={setRoute.error} />
    </section>
  );
}

function ProviderRow({
  provider,
  isDefault,
  canEdit,
}: {
  provider: Provider;
  isDefault: boolean;
  canEdit: boolean;
}) {
  const id = useId();
  const [editing, setEditing] = useState(false);
  const [baseUrl, setBaseUrl] = useState("");
  const [apiKey, setApiKey] = useState("");
  const [model, setModel] = useState("");
  const save = useSaveProvider();
  const reset = useResetProvider();

  const close = () => {
    setEditing(false);
    setBaseUrl("");
    setApiKey("");
    setModel("");
    save.reset();
  };
  const testAndSave = () =>
    save.mutate(
      {
        provider: provider.id,
        body: {
          base_url: baseUrl.trim() || null,
          api_key: apiKey.trim() || null,
          chat_model: model || null,
        },
      },
      { onSuccess: close },
    );

  const summary = [
    provider.api_key_masked ? `key ${provider.api_key_masked}` : "no key",
    provider.base_url_required ? (provider.base_url ?? "no URL") : null,
    provider.chat_model,
  ]
    .filter(Boolean)
    .join(" · ");

  return (
    <section className="space-y-3 border-b py-4 last:border-b-0 last:pb-0">
      <div className="flex flex-wrap items-center gap-x-4 gap-y-2">
        <div className="min-w-0 flex-1">
          <h3 className="flex items-center gap-2 font-medium">
            {provider.label}
            {isDefault ? <Badge variant="secondary">Default</Badge> : null}
            {provider.configured ? null : <Badge variant="outline">Not set up</Badge>}
          </h3>
          <p className="truncate font-mono text-muted-foreground text-xs">
            {summary}
            {provider.saved.length > 0 ? " · saved here" : provider.configured ? " · .env" : ""}
          </p>
        </div>
        {canEdit && !editing ? (
          <div className="flex gap-2">
            {provider.saved.length > 0 ? (
              <Button
                variant="ghost"
                size="sm"
                disabled={reset.isPending}
                onClick={() => reset.mutate(provider.id)}
                title="Forget the values saved here; .env applies again"
              >
                <RotateCcw />
                Use .env
              </Button>
            ) : null}
            <Button variant="outline" size="sm" onClick={() => setEditing(true)}>
              {provider.configured ? "Edit" : "Set up"}
            </Button>
          </div>
        ) : null}
      </div>

      {editing ? (
        <div className="space-y-3 rounded-md border bg-muted/30 p-4">
          <div className="grid gap-3 sm:grid-cols-2">
            {provider.base_url_required ? (
              <div className="space-y-1.5 sm:col-span-2">
                <Label htmlFor={`${id}-url`}>Endpoint URL</Label>
                <Input
                  id={`${id}-url`}
                  value={baseUrl}
                  onChange={(event) => setBaseUrl(event.target.value)}
                  placeholder={provider.base_url ?? URL_PLACEHOLDER[provider.id]}
                  className="font-mono"
                  autoComplete="off"
                />
              </div>
            ) : null}
            <div className="space-y-1.5">
              <Label htmlFor={`${id}-key`}>API key</Label>
              <Input
                id={`${id}-key`}
                type="password"
                value={apiKey}
                onChange={(event) => setApiKey(event.target.value)}
                placeholder={
                  provider.api_key_masked ? `Keep ${provider.api_key_masked}` : "Paste the key"
                }
                autoComplete="new-password"
              />
            </div>
            <div className="space-y-1.5">
              <Label htmlFor={`${id}-model`}>Default model</Label>
              <ModelPicker
                id={`${id}-model`}
                value={model || provider.chat_model || ""}
                provider={provider.id}
                listed={provider.lists_models && provider.configured}
                embeddings={false}
                disabled={save.isPending}
                onSelect={setModel}
              />
            </div>
          </div>
          <ErrorAlert error={save.error} />
          <div className="flex flex-wrap items-center gap-2">
            <Button size="sm" disabled={save.isPending} onClick={testAndSave}>
              {save.isPending ? (
                <>
                  <Loader2 className="animate-spin" />
                  Testing…
                </>
              ) : (
                "Test and save"
              )}
            </Button>
            <Button variant="ghost" size="sm" disabled={save.isPending} onClick={close}>
              Cancel
            </Button>
            <p className="text-muted-foreground text-xs">
              One short call checks the key and model; nothing is saved if it fails.
            </p>
          </div>
        </div>
      ) : null}
      {editing ? null : <ErrorAlert error={reset.error} />}
    </section>
  );
}

export function ProvidersPane({ settings }: { settings: Settings }) {
  return (
    <div className="space-y-5">
      <DefaultProvider settings={settings} />
      <div>
        {settings.providers.map((provider) => (
          <ProviderRow
            key={provider.id}
            provider={provider}
            isDefault={provider.id === settings.route}
            canEdit={settings.can_edit}
          />
        ))}
      </div>
    </div>
  );
}
