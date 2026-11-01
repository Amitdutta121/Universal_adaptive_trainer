"use client";

/**
 * Picking a course's question types: grouped checkboxes, each with an example in the subject's
 * terms, and how the ticked types are graded. Used by course Settings; a new course starts from
 * its subject's defaults (`default_types`) and is not asked (ADR-054).
 *
 * Everything comes from `GET /api/courses/catalog`: only types the app can generate and grade
 * can be ticked; the rest are listed as "Coming soon".
 */

import { ChevronDownIcon, InfoIcon } from "lucide-react";
import { useState } from "react";
import { Badge } from "@/components/ui/badge";
import type { Schemas } from "@/lib/api/types";
import { cn } from "@/lib/utils";

type Catalog = Schemas["AssessmentCatalogResponse"];
type QuestionTypeOut = Schemas["QuestionTypeOut"];
type SubjectPresetOut = Schemas["SubjectPresetOut"];

function TypeCheckbox({
  type,
  example,
  checked,
  recommended,
  onChange,
}: {
  type: QuestionTypeOut;
  example: string;
  checked: boolean;
  recommended: boolean;
  onChange: (next: boolean) => void;
}) {
  const inputId = `type-${type.id}`;
  return (
    <label
      htmlFor={inputId}
      className={cn(
        "flex items-start gap-3 rounded-lg border px-3 py-2.5 transition-colors",
        type.offerable ? "cursor-pointer hover:bg-muted/40" : "cursor-not-allowed opacity-60",
        checked && "border-primary/50 bg-[var(--accent-wash)]/40",
      )}
    >
      <input
        id={inputId}
        type="checkbox"
        className="mt-0.5 size-4 accent-[var(--accent-solid)]"
        checked={checked}
        disabled={!type.offerable}
        onChange={(event) => onChange(event.target.checked)}
      />
      <span className="min-w-0 flex-1">
        <span className="flex flex-wrap items-center gap-2">
          <span className="font-medium text-sm">{type.label}</span>
          {!type.offerable ? (
            <Badge variant="outline" className="font-normal text-[11px]">
              Coming soon
            </Badge>
          ) : recommended ? (
            <Badge variant="secondary" className="font-normal text-[11px]">
              Recommended
            </Badge>
          ) : null}
          {type.ai_graded ? (
            <span
              className="rounded px-1.5 py-0.5 font-medium text-[11px]"
              style={{ background: "var(--warn-wash)", color: "var(--warn-solid)" }}
            >
              AI-graded · practice only, never counts toward mastery
            </span>
          ) : null}
        </span>
        <span className="mt-0.5 block text-muted-foreground text-xs">
          Students answer with {type.widget}
        </span>
        {example ? (
          <span className="mt-1 block text-muted-foreground text-xs italic">{example}</span>
        ) : null}
      </span>
    </label>
  );
}

export function TypeGroups({
  catalog,
  subject,
  chosen,
  setType,
}: {
  catalog: Catalog;
  subject: SubjectPresetOut;
  chosen: ReadonlySet<string>;
  setType: (id: string, on: boolean) => void;
}) {
  const [showMore, setShowMore] = useState(false);
  const recommended = new Set([...subject.default_types, ...subject.coming_soon_types]);
  const primary = catalog.groups.filter((group) => subject.primary_groups.includes(group.id));
  const others = catalog.groups.filter((group) => !subject.primary_groups.includes(group.id));

  const renderGroup = (group: Catalog["groups"][number]) => {
    const types = catalog.question_types.filter((type) => type.group === group.id);
    if (types.length === 0) return null;
    return (
      <section key={group.id} className="space-y-2">
        <div className="flex items-baseline gap-2">
          <h3 className="font-medium text-sm">{group.title}</h3>
          <span className="text-muted-foreground text-xs">{group.hint}</span>
        </div>
        <div className="grid gap-2 md:grid-cols-2">
          {types.map((type) => (
            <TypeCheckbox
              key={type.id}
              type={type}
              example={subject.examples[type.id] ?? ""}
              checked={chosen.has(type.id)}
              recommended={recommended.has(type.id)}
              onChange={(next) => setType(type.id, next)}
            />
          ))}
        </div>
      </section>
    );
  };

  return (
    <div className="space-y-5">
      {primary.map(renderGroup)}
      {others.length > 0 ? (
        <div className="rounded-lg border">
          <button
            type="button"
            aria-expanded={showMore}
            onClick={() => setShowMore((open) => !open)}
            className="flex w-full items-center gap-2 px-3 py-2 text-left text-sm"
          >
            More question types
            <span className="text-muted-foreground text-xs">
              {others.map((group) => group.title).join(" · ")}
            </span>
            <ChevronDownIcon
              className={cn("ml-auto size-4 transition-transform", showMore && "rotate-180")}
            />
          </button>
          {showMore ? (
            <div className="space-y-5 border-t px-3 py-3">{others.map(renderGroup)}</div>
          ) : null}
        </div>
      ) : null}
    </div>
  );
}

/** How the chosen types will be graded, in plain words. Mirrors the server's derivation. */
function gradingNote(catalog: Catalog, chosen: ReadonlySet<string>) {
  const built = new Set(catalog.capabilities.filter((cap) => cap.built).map((cap) => cap.id));
  const needed = new Set<string>();
  for (const type of catalog.question_types) {
    if (!chosen.has(type.id)) continue;
    const grader = type.graded_by.find((id) => built.has(id));
    if (grader) needed.add(grader);
    for (const need of type.also_needs) needed.add(need);
  }
  return catalog.capabilities.filter((cap) => needed.has(cap.id));
}

/** "How these are graded", collapsed by default. */
export function GradingNote({
  catalog,
  chosen,
}: {
  catalog: Catalog;
  chosen: ReadonlySet<string>;
}) {
  const [open, setOpen] = useState(false);
  const grading = gradingNote(catalog, chosen);
  return (
    <div className="rounded-lg border bg-muted/30">
      <button
        type="button"
        aria-expanded={open}
        onClick={() => setOpen((value) => !value)}
        className="flex w-full items-center gap-2 px-3 py-2 text-left text-muted-foreground text-xs"
      >
        <InfoIcon className="size-3.5" />
        How these are graded
        <ChevronDownIcon
          className={cn("ml-auto size-3.5 transition-transform", open && "rotate-180")}
        />
      </button>
      {open ? (
        <ul className="space-y-1 border-t px-3 py-2 text-xs">
          {grading.map((cap) => (
            <li key={cap.id}>
              <span className="font-medium">{cap.label}:</span>{" "}
              <span className="text-muted-foreground">{cap.description}</span>
            </li>
          ))}
          {grading.length === 0 ? (
            <li className="text-muted-foreground">Tick a question type to see how it is graded.</li>
          ) : null}
        </ul>
      ) : null}
    </div>
  );
}
