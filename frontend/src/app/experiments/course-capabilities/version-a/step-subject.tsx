"use client";

import { CheckIcon } from "lucide-react";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { cn } from "@/lib/utils";
import { CAPABILITIES_BY_ID, isSelectable, SUBJECT_PRESETS } from "../mock-capabilities";

export function StepSubject({
  courseName,
  onCourseName,
  presetId,
  onPreset,
  customised,
}: {
  courseName: string;
  onCourseName: (name: string) => void;
  presetId: string | null;
  onPreset: (id: string) => void;
  /** True when the capabilities were edited after the preset was picked. */
  customised: boolean;
}) {
  return (
    <div className="flex flex-col gap-6">
      <div className="flex max-w-md flex-col gap-1.5">
        <Label htmlFor="course-name">
          Course name <span className="font-normal text-muted-foreground">(optional)</span>
        </Label>
        <Input
          id="course-name"
          value={courseName}
          onChange={(event) => onCourseName(event.target.value)}
          placeholder="e.g. CS 135 · Intro to Programming"
        />
      </div>

      <fieldset className="flex flex-col gap-3">
        <legend className="mb-1 font-medium text-sm">Subject</legend>
        <p className="-mt-1 text-muted-foreground text-sm">
          Sets the starting capabilities. You can adjust them in the next step.
          {customised && presetId ? " Picking another subject replaces your changes." : null}
        </p>
        <div className="grid gap-3 sm:grid-cols-2">
          {SUBJECT_PRESETS.map((preset) => {
            const selected = preset.id === presetId;
            const caps = preset.capabilities.flatMap((id) => {
              const cap = CAPABILITIES_BY_ID[id];
              return cap ? [cap] : [];
            });
            return (
              <button
                key={preset.id}
                type="button"
                aria-pressed={selected}
                onClick={() => onPreset(preset.id)}
                className={cn(
                  "flex flex-col gap-2 rounded-lg border bg-card p-4 text-left outline-none transition-colors hover:border-foreground/25 focus-visible:ring-3 focus-visible:ring-ring/50",
                  selected &&
                    "border-[var(--accent-solid)] bg-[var(--accent-wash)]/40 hover:border-[var(--accent-solid)]",
                )}
              >
                <div className="flex items-start justify-between gap-3">
                  <span className="font-medium text-sm">{preset.label}</span>
                  <span
                    aria-hidden
                    className={cn(
                      "flex size-4 shrink-0 items-center justify-center rounded-full border",
                      selected &&
                        "border-[var(--accent-solid)] bg-[var(--accent-solid)] text-white",
                    )}
                  >
                    {selected ? <CheckIcon className="size-3" /> : null}
                  </span>
                </div>
                <span className="text-muted-foreground text-sm">{preset.blurb}</span>
                <ul className="mt-1 flex flex-wrap gap-1.5" aria-label="Turns on">
                  {caps.map((cap) => {
                    const buildable = isSelectable(cap);
                    return (
                      <li
                        key={cap.id}
                        className={cn(
                          "rounded border px-1.5 py-0.5 text-xs",
                          buildable
                            ? "bg-background text-foreground"
                            : "border-dashed text-muted-foreground",
                        )}
                      >
                        {cap.label}
                        {buildable ? null : " · not built yet"}
                      </li>
                    );
                  })}
                </ul>
              </button>
            );
          })}
        </div>
      </fieldset>
    </div>
  );
}
