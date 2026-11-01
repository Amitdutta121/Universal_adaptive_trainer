"use client";

/**
 * A searchable model picker for one role (Task 44 follow-up).
 *
 * Lists the chosen provider's models, grouped by vendor; OpenRouter's also carry each model's
 * context window and price, so a professor can compare before choosing. Any id can still be
 * used: typing one that is not listed offers it as a custom entry, which covers Azure
 * deployments and providers whose list can't be read. The embeddings role lists only
 * embedding models.
 */

import { Check, ChevronsUpDown, Loader2 } from "lucide-react";
import { useMemo, useState } from "react";
import { Button } from "@/components/ui/button";
import {
  Command,
  CommandEmpty,
  CommandGroup,
  CommandInput,
  CommandItem,
  CommandList,
} from "@/components/ui/command";
import { Popover, PopoverContent, PopoverTrigger } from "@/components/ui/popover";
import { useProviderModels } from "@/lib/api/queries";
import type { Schemas } from "@/lib/api/types";
import { cn } from "@/lib/utils";

type ProviderModel = Schemas["ProviderModel"];
type ProviderId = Schemas["ProviderOut"]["id"];

export function formatContext(tokens: number | null | undefined): string | null {
  if (!tokens) return null;
  if (tokens >= 1_000_000) return `${+(tokens / 1_000_000).toFixed(1)}M`;
  return `${Math.round(tokens / 1000)}K`;
}

function formatPrice(value: number): string {
  if (value === 0) return "$0";
  return value < 0.1 ? `$${+value.toFixed(3)}` : `$${+value.toFixed(2)}`;
}

/** "$2.5 / $10" per million input / output tokens; "Free" when both are zero. */
export function formatPricing(model: ProviderModel): string | null {
  const { prompt_price: input, completion_price: output } = model;
  if (input == null || output == null) return null;
  if (input === 0 && output === 0) return "Free";
  return `${formatPrice(input)} / ${formatPrice(output)}`;
}

function vendorOf(id: string): string {
  return id.includes("/") ? id.split("/")[0] : "other";
}

function ModelMeta({ model }: { model: ProviderModel }) {
  const context = formatContext(model.context_length);
  const pricing = formatPricing(model);
  if (!context && !pricing) return null;
  return (
    <span
      className="ml-auto flex shrink-0 gap-3 text-muted-foreground text-xs tabular-nums"
      title="Context window · price per million input / output tokens"
    >
      {context ? <span>{context}</span> : null}
      {pricing ? <span className="w-24 text-right">{pricing}</span> : null}
    </span>
  );
}

export function ModelPicker({
  id,
  value,
  provider,
  listed,
  embeddings,
  disabled,
  disabledReason,
  placeholder = "Choose a model",
  onSelect,
}: {
  id?: string;
  /** The model in effect: the edited one, else the saved or .env one. */
  value: string;
  provider: ProviderId;
  /** Whether the provider's model list can be read (it has one, and a key to read it with). */
  listed: boolean;
  /** The embeddings role lists only embedding models. */
  embeddings: boolean;
  disabled?: boolean;
  disabledReason?: string;
  placeholder?: string;
  onSelect: (model: string) => void;
}) {
  const [open, setOpen] = useState(false);
  const [search, setSearch] = useState("");
  const models = useProviderModels(provider, listed && open);

  const available = useMemo(() => {
    const all = models.data ?? [];
    return embeddings ? all.filter((model) => /embed/i.test(model.id)) : all;
  }, [models.data, embeddings]);
  const groups = useMemo(() => {
    const byVendor = new Map<string, ProviderModel[]>();
    for (const model of available) {
      const vendor = vendorOf(model.id);
      byVendor.set(vendor, [...(byVendor.get(vendor) ?? []), model]);
    }
    return [...byVendor.entries()];
  }, [available]);
  const current = available.find((model) => model.id === value) ?? null;
  const typed = search.trim();
  const offerCustom = typed.length > 0 && !available.some((model) => model.id === typed);

  const choose = (model: string) => {
    onSelect(model);
    setOpen(false);
    setSearch("");
  };

  return (
    // Modal, so the list scrolls inside the settings dialog's scroll lock.
    <Popover open={open} onOpenChange={setOpen} modal>
      <PopoverTrigger asChild>
        <Button
          id={id}
          variant="outline"
          role="combobox"
          aria-expanded={open}
          aria-label="Model"
          disabled={disabled}
          title={disabled ? disabledReason : undefined}
          className="h-auto w-full justify-between gap-2 py-1.5 text-left font-normal"
        >
          <span className="min-w-0">
            <span className={cn("block truncate text-sm", !value && "text-muted-foreground")}>
              {current?.name ?? (value || placeholder)}
            </span>
            {current ? (
              <span className="block truncate font-mono text-muted-foreground text-xs">
                {value}
              </span>
            ) : null}
          </span>
          <ChevronsUpDown className="opacity-50" />
        </Button>
      </PopoverTrigger>
      <PopoverContent align="end" className="w-[34rem] max-w-[calc(100vw-2rem)] p-0">
        <Command>
          <CommandInput
            placeholder={listed ? "Search models or type an id…" : "Type a model id…"}
            value={search}
            onValueChange={setSearch}
          />
          <CommandList className="max-h-[22rem]">
            {models.isFetching && !models.data ? (
              <div className="flex items-center gap-2 px-3 py-6 text-muted-foreground text-sm">
                <Loader2 className="size-4 animate-spin" />
                Loading models…
              </div>
            ) : null}
            <CommandEmpty>
              {models.isError
                ? "Could not load the model list. Type a model id instead."
                : listed && embeddings
                  ? "No embedding models are listed. Type the model id."
                  : "No model matches. Type its full id."}
            </CommandEmpty>
            {groups.map(([vendor, items]) => (
              <CommandGroup key={vendor} heading={vendor}>
                {items.map((model) => (
                  <CommandItem
                    key={model.id}
                    value={model.id}
                    keywords={[model.name]}
                    onSelect={() => choose(model.id)}
                  >
                    <Check
                      className={cn("size-4", model.id === value ? "opacity-100" : "opacity-0")}
                    />
                    <span className="min-w-0">
                      <span className="block truncate">{model.name}</span>
                      <span className="block truncate font-mono text-muted-foreground text-xs">
                        {model.id}
                      </span>
                    </span>
                    <ModelMeta model={model} />
                  </CommandItem>
                ))}
              </CommandGroup>
            ))}
            {/* Last, so Enter picks the best listed match rather than the raw text. */}
            {offerCustom ? (
              <CommandGroup heading="Custom" forceMount>
                <CommandItem value={`custom:${typed}`} forceMount onSelect={() => choose(typed)}>
                  Use <span className="font-mono">{typed}</span>
                </CommandItem>
              </CommandGroup>
            ) : null}
          </CommandList>
        </Command>
      </PopoverContent>
    </Popover>
  );
}
