"use client";

/**
 * Version A · Guided setup. The capability setup as it appears when a professor CREATES a course:
 * a three-step stepper.
 *   1. Subject — pick a preset (and optionally name the course); it seeds the enabled set.
 *   2. Capabilities — adjust the enabled graders, grouped by family. Planned ones are locked.
 *   3. Review — the derived question types: allowed (with a per-type switch-off), and the ones
 *      nothing enabled can grade, with the reason.
 * State lives in this component only; "Create course" saves nothing.
 */

import { ArrowLeftIcon, ArrowRightIcon, CheckIcon, InfoIcon } from "lucide-react";
import { useMemo, useState } from "react";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Separator } from "@/components/ui/separator";
import { cn } from "@/lib/utils";
import {
  CAPABILITIES_BY_ID,
  isSelectable,
  SUBJECT_PRESETS,
  type SubjectPreset,
  typeAvailability,
} from "../mock-capabilities";
import { StepCapabilities } from "./step-capabilities";
import { StepReview } from "./step-review";
import { StepSubject } from "./step-subject";

const STEPS = [
  { title: "Subject", description: "Choose a starting point for the course." },
  { title: "Capabilities", description: "Choose how student answers can be checked." },
  { title: "Review", description: "Check which question types this course will use." },
] as const;

/** A preset's capabilities, minus any that have no grader yet. */
function selectableFromPreset(preset: SubjectPreset): Set<string> {
  return new Set(
    preset.capabilities.filter((id) => {
      const cap = CAPABILITIES_BY_ID[id];
      return cap !== undefined && isSelectable(cap);
    }),
  );
}

export function VersionA() {
  const [step, setStep] = useState(0);
  const [courseName, setCourseName] = useState("");
  const [presetId, setPresetId] = useState<string | null>(null);
  const [enabled, setEnabled] = useState<Set<string>>(new Set());
  const [switchedOff, setSwitchedOff] = useState<Set<string>>(new Set());
  const [customised, setCustomised] = useState(false);
  const [submitted, setSubmitted] = useState(false);

  const availability = useMemo(
    () => typeAvailability(enabled, switchedOff),
    [enabled, switchedOff],
  );
  const allowedCount = availability.filter((entry) => entry.allowed).length;
  const preset = SUBJECT_PRESETS.find((entry) => entry.id === presetId) ?? null;

  function pickPreset(id: string) {
    const next = SUBJECT_PRESETS.find((entry) => entry.id === id);
    if (!next) return;
    setPresetId(id);
    setEnabled(selectableFromPreset(next));
    setSwitchedOff(new Set());
    setCustomised(false);
    setSubmitted(false);
  }

  function toggleCapability(id: string, on: boolean) {
    setEnabled((prev) => {
      const next = new Set(prev);
      if (on) next.add(id);
      else next.delete(id);
      return next;
    });
    setCustomised(true);
    setSubmitted(false);
  }

  function switchType(typeId: string, on: boolean) {
    setSwitchedOff((prev) => {
      const next = new Set(prev);
      if (on) next.delete(typeId);
      else next.add(typeId);
      return next;
    });
    setSubmitted(false);
  }

  function createCourse() {
    // TODO(real): POST the course (name, subject preset, enabled capability ids, switched-off
    // question type ids) to the courses API, then route to the new course.
    setSubmitted(true);
  }

  const canAdvance = step === 0 ? presetId !== null : step === 1 ? enabled.size > 0 : true;
  const current = STEPS[step] ?? STEPS[0];

  return (
    <div className="mx-auto flex w-full max-w-4xl flex-col gap-5">
      <div>
        <h1 className="font-semibold text-lg">New course</h1>
        <p className="text-muted-foreground text-sm">
          Set up what the course can grade. This decides which question types the AI may generate.
        </p>
      </div>

      <nav aria-label="Setup steps">
        <ol className="flex items-center gap-2">
          {STEPS.map((entry, index) => {
            const done = index < step;
            const active = index === step;
            // A later step is reachable only when every earlier step is complete.
            const reachable =
              index <= step ||
              (index === 1 && presetId !== null) ||
              (index === 2 && presetId !== null && enabled.size > 0);
            return (
              <li key={entry.title} className="flex flex-1 items-center gap-2">
                <button
                  type="button"
                  onClick={() => setStep(index)}
                  disabled={!reachable}
                  aria-current={active ? "step" : undefined}
                  className={cn(
                    "flex items-center gap-2 rounded-md py-1 pr-2 text-sm outline-none focus-visible:ring-3 focus-visible:ring-ring/50 disabled:cursor-not-allowed",
                    active ? "font-medium text-foreground" : "text-muted-foreground",
                  )}
                >
                  <span
                    aria-hidden
                    className={cn(
                      "flex size-6 shrink-0 items-center justify-center rounded-full border text-xs tabular-nums",
                      active && "border-[var(--accent-solid)] bg-[var(--accent-solid)] text-white",
                      done && "border-[var(--accent-solid)] text-[var(--accent-text)]",
                    )}
                  >
                    {done ? <CheckIcon className="size-3.5" /> : index + 1}
                  </span>
                  <span>
                    <span className="sr-only">Step {index + 1}: </span>
                    {entry.title}
                    {done ? <span className="sr-only"> (complete)</span> : null}
                  </span>
                </button>
                {index < STEPS.length - 1 ? (
                  <span
                    aria-hidden
                    className={cn("h-px flex-1 bg-border", done && "bg-[var(--accent-solid)]")}
                  />
                ) : null}
              </li>
            );
          })}
        </ol>
      </nav>

      <Card>
        <CardHeader className="border-b">
          <CardTitle>
            {step + 1}. {current.title}
          </CardTitle>
          <CardDescription>{current.description}</CardDescription>
        </CardHeader>
        <CardContent>
          {step === 0 ? (
            <StepSubject
              courseName={courseName}
              onCourseName={setCourseName}
              presetId={presetId}
              onPreset={pickPreset}
              customised={customised}
            />
          ) : step === 1 ? (
            <StepCapabilities enabled={enabled} onToggle={toggleCapability} />
          ) : (
            <StepReview
              courseName={courseName}
              presetLabel={preset?.label ?? null}
              enabledCount={enabled.size}
              availability={availability}
              onSwitch={switchType}
            />
          )}
        </CardContent>
        <Separator />
        <div className="flex flex-wrap items-center gap-3 px-4">
          <Button
            variant="outline"
            onClick={() => setStep((value) => Math.max(0, value - 1))}
            disabled={step === 0}
          >
            <ArrowLeftIcon data-icon="inline-start" />
            Back
          </Button>
          <p className="mr-auto text-muted-foreground text-sm" aria-live="polite">
            {presetId === null
              ? "Pick a subject to continue."
              : `${allowedCount} question ${allowedCount === 1 ? "type" : "types"} · ${enabled.size} ${enabled.size === 1 ? "capability" : "capabilities"}`}
          </p>
          {submitted ? (
            <p className="flex items-center gap-1.5 text-muted-foreground text-sm" role="status">
              <InfoIcon className="size-4" aria-hidden />
              Prototype — nothing is saved.
            </p>
          ) : null}
          {step < STEPS.length - 1 ? (
            <Button onClick={() => setStep((value) => value + 1)} disabled={!canAdvance}>
              Next
              <ArrowRightIcon data-icon="inline-end" />
            </Button>
          ) : (
            <Button onClick={createCourse} disabled={allowedCount === 0}>
              Create course
            </Button>
          )}
        </div>
      </Card>
    </div>
  );
}
