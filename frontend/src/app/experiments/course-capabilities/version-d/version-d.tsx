"use client";

/**
 * Version D · Pick question types. A rework of version A from the professor's side: they choose
 * what students will DO (question types), never which graders run.
 *   1. Subject — a preset, described by the question types it gives.
 *   2. Question types — pre-ticked from the preset, each with an example. AI grading is flagged on
 *      the type itself. Types with no grader yet are listed as "Coming soon".
 * Capabilities are derived behind the scenes: a ticked type turns on a capability that grades it
 * plus whatever it also needs (ticking "Coding" turns on Python tests and Run Python). Grader ids
 * and dependencies never appear; a collapsed "How these are graded" note explains it in plain words.
 * State lives in this component only; "Create course" saves nothing.
 */

import { ArrowLeftIcon, ArrowRightIcon, CheckIcon, ChevronDownIcon, InfoIcon } from "lucide-react";
import { useMemo, useState } from "react";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { cn } from "@/lib/utils";
import {
  CAPABILITIES_BY_ID,
  isSelectable,
  QUESTION_TYPES,
  type QuestionType,
  SUBJECT_PRESETS,
  type SubjectPreset,
  typeAvailability,
} from "../mock-capabilities";

/** What a student sees, in one line per type. TODO(real): comes with each type's definition. */
const EXAMPLE: Record<string, string> = {
  multiple_choice: "Which of these is a mutable type? (a) tuple (b) list (c) str",
  true_false: "True or false: a list can hold values of different types.",
  short_answer: "What does len('abc') return?",
  parsons: "Put these lines in order so the loop prints 1 to 5.",
  output_prediction: "What does this code print?",
  code_completion: "Fill in the missing line so the function returns the largest value.",
  debugging: "This loop never stops. Fix it.",
  coding: "Write factorial(n). Graded by hidden tests, with partial credit.",
  short_explanation: "In two sentences, explain why the loop never ends.",
  numeric_response: "A ball falls from rest. Its speed after 2 s, in m/s?",
  equation_response: "Differentiate x² sin x.",
};

/** Plain-language groups a professor recognises. TODO(real): part of the type registry. */
const GROUPS: ReadonlyArray<{ title: string; hint: string; types: readonly string[] }> = [
  {
    title: "Quick checks",
    hint: "Fast to answer, marked instantly.",
    types: ["multiple_choice", "true_false", "short_answer"],
  },
  {
    title: "Code",
    hint: "Marked by running the code.",
    types: ["parsons", "output_prediction", "code_completion", "debugging", "coding"],
  },
  {
    title: "Numbers and maths",
    hint: "Marked by checking the value or the formula.",
    types: ["numeric_response", "equation_response"],
  },
  {
    title: "Written answers",
    hint: "Marked by AI against a rubric.",
    types: ["short_explanation"],
  },
];

const TYPES_BY_ID: Record<string, QuestionType> = Object.fromEntries(
  QUESTION_TYPES.map((type) => [type.id, type]),
);

function built(id: string): boolean {
  const capability = CAPABILITIES_BY_ID[id];
  return capability !== undefined && isSelectable(capability);
}

/** A type can be offered when something built can grade it and everything it needs is built. */
function isOfferable(type: QuestionType): boolean {
  return type.gradedBy.some(built) && type.alsoNeeds.every(built);
}

function isAiGraded(type: QuestionType): boolean {
  return type.gradedBy.every((id) => CAPABILITIES_BY_ID[id]?.deterministic === false);
}

/** The types a preset gives: everything its built capabilities can grade. */
function typesForPreset(preset: SubjectPreset): Set<string> {
  const enabled = new Set(preset.capabilities.filter(built));
  return new Set(
    typeAvailability(enabled)
      .filter((entry) => entry.possible)
      .map((entry) => entry.type.id),
  );
}

/** The capabilities the chosen types need, worked out so the professor never picks graders. */
function derivedCapabilities(types: ReadonlySet<string>): Set<string> {
  const capabilities = new Set<string>();
  for (const id of types) {
    const type = TYPES_BY_ID[id];
    if (!type) continue;
    const grader = type.gradedBy.find(built);
    if (grader) capabilities.add(grader);
    for (const need of type.alsoNeeds) capabilities.add(need);
  }
  return capabilities;
}

function TypeCheckbox({
  type,
  checked,
  onChange,
}: {
  type: QuestionType;
  checked: boolean;
  onChange: (next: boolean) => void;
}) {
  const offerable = isOfferable(type);
  const inputId = `type-${type.id}`;
  return (
    <label
      htmlFor={inputId}
      className={cn(
        "flex items-start gap-3 rounded-lg border px-3 py-2.5 transition-colors",
        offerable ? "cursor-pointer hover:bg-muted/40" : "cursor-not-allowed opacity-60",
        checked && "border-primary/50 bg-[var(--accent-wash)]/40",
      )}
    >
      <input
        id={inputId}
        type="checkbox"
        className="mt-0.5 size-4 accent-[var(--accent-solid)]"
        checked={checked}
        disabled={!offerable}
        onChange={(event) => onChange(event.target.checked)}
      />
      <span className="min-w-0 flex-1">
        <span className="flex flex-wrap items-center gap-2">
          <span className="font-medium text-sm">{type.label}</span>
          {!offerable ? (
            <Badge variant="outline" className="font-normal text-[11px]">
              Coming soon
            </Badge>
          ) : null}
          {isAiGraded(type) ? (
            <span
              className="rounded px-1.5 py-0.5 font-medium text-[11px]"
              style={{ background: "var(--warn-wash)", color: "var(--warn-solid)" }}
            >
              AI-graded · practice only, never counts toward mastery
            </span>
          ) : null}
        </span>
        <span className="mt-0.5 block text-muted-foreground text-xs">
          Students answer with: {type.widget.toLowerCase()}
        </span>
        <span className="mt-1 block text-muted-foreground text-xs italic">{EXAMPLE[type.id]}</span>
      </span>
    </label>
  );
}

export function VersionD() {
  const [step, setStep] = useState<0 | 1>(0);
  const [courseName, setCourseName] = useState("");
  const [presetId, setPresetId] = useState<string | null>(null);
  const [types, setTypes] = useState<Set<string>>(new Set());
  const [showHow, setShowHow] = useState(false);
  const [submitted, setSubmitted] = useState(false);

  const preset = SUBJECT_PRESETS.find((entry) => entry.id === presetId) ?? null;
  const capabilities = useMemo(() => derivedCapabilities(types), [types]);

  function pickPreset(next: SubjectPreset) {
    setPresetId(next.id);
    setTypes(typesForPreset(next));
    setSubmitted(false);
  }

  function setType(id: string, on: boolean) {
    setTypes((previous) => {
      const next = new Set(previous);
      if (on) next.add(id);
      else next.delete(id);
      return next;
    });
    setSubmitted(false);
  }

  return (
    <div className="mx-auto max-w-4xl space-y-5">
      <div>
        <h1 className="font-semibold text-xl">New course</h1>
        <p className="text-muted-foreground text-sm">
          Choose the subject, then the kinds of questions students will answer.
        </p>
      </div>

      <ol className="flex items-center gap-3 text-sm" aria-label="Steps">
        {["Subject", "Question types"].map((title, index) => (
          <li
            key={title}
            aria-current={step === index ? "step" : undefined}
            className="flex items-center gap-2"
          >
            <span
              className={cn(
                "flex size-6 items-center justify-center rounded-full border text-xs",
                step === index && "border-primary bg-primary text-primary-foreground",
                step > index && "border-primary text-primary",
              )}
            >
              {step > index ? <CheckIcon className="size-3.5" /> : index + 1}
            </span>
            <span className={step === index ? "font-medium" : "text-muted-foreground"}>
              {title}
            </span>
            {index === 0 ? <span className="mx-2 h-px w-16 bg-border" aria-hidden /> : null}
          </li>
        ))}
      </ol>

      <Card>
        {step === 0 ? (
          <>
            <CardHeader>
              <CardTitle className="text-base">1. Subject</CardTitle>
              <CardDescription>
                It decides which question types are ticked to start with.
              </CardDescription>
            </CardHeader>
            <CardContent className="space-y-5">
              <div className="max-w-md space-y-2">
                <Label htmlFor="d-course-name">
                  Course name <span className="text-muted-foreground">(optional)</span>
                </Label>
                <Input
                  id="d-course-name"
                  value={courseName}
                  placeholder="e.g. CS 135 · Intro to Programming"
                  onChange={(event) => setCourseName(event.target.value)}
                />
              </div>
              <div className="grid gap-3 md:grid-cols-2">
                {SUBJECT_PRESETS.map((entry) => {
                  const given = [...typesForPreset(entry)].map((id) => TYPES_BY_ID[id]?.label);
                  const selected = entry.id === presetId;
                  return (
                    <button
                      key={entry.id}
                      type="button"
                      aria-pressed={selected}
                      onClick={() => pickPreset(entry)}
                      className={cn(
                        "rounded-xl border p-4 text-left transition-colors hover:bg-muted/40",
                        selected && "border-primary ring-1 ring-primary",
                      )}
                    >
                      <div className="font-medium text-sm">{entry.label}</div>
                      <div className="mt-1 text-muted-foreground text-xs">
                        {given.length > 0 ? given.join(" · ") : "Pick question types yourself"}
                      </div>
                    </button>
                  );
                })}
              </div>
            </CardContent>
          </>
        ) : (
          <>
            <CardHeader>
              <CardTitle className="text-base">2. Question types</CardTitle>
              <CardDescription>
                Ticked from {preset?.label ?? "your subject"}. The AI only writes questions of the
                ticked types. You can change this later in course settings.
              </CardDescription>
            </CardHeader>
            <CardContent className="space-y-5">
              {GROUPS.map((group) => (
                <section key={group.title} className="space-y-2">
                  <div className="flex items-baseline gap-2">
                    <h3 className="font-medium text-sm">{group.title}</h3>
                    <span className="text-muted-foreground text-xs">{group.hint}</span>
                  </div>
                  <div className="grid gap-2 md:grid-cols-2">
                    {group.types.map((id) => {
                      const type = TYPES_BY_ID[id];
                      return type ? (
                        <TypeCheckbox
                          key={id}
                          type={type}
                          checked={types.has(id)}
                          onChange={(next) => setType(id, next)}
                        />
                      ) : null;
                    })}
                  </div>
                </section>
              ))}

              <div className="rounded-lg border bg-muted/30">
                <button
                  type="button"
                  aria-expanded={showHow}
                  onClick={() => setShowHow((open) => !open)}
                  className="flex w-full items-center gap-2 px-3 py-2 text-left text-muted-foreground text-xs"
                >
                  <InfoIcon className="size-3.5" />
                  How these are graded
                  <ChevronDownIcon
                    className={cn("ml-auto size-3.5 transition-transform", showHow && "rotate-180")}
                  />
                </button>
                {showHow ? (
                  <ul className="space-y-1 border-t px-3 py-2 text-xs">
                    {[...capabilities].map((id) => {
                      const capability = CAPABILITIES_BY_ID[id];
                      return capability ? (
                        <li key={id}>
                          <span className="font-medium">{capability.label}:</span>{" "}
                          <span className="text-muted-foreground">{capability.card}</span>
                        </li>
                      ) : null;
                    })}
                    {capabilities.size === 0 ? (
                      <li className="text-muted-foreground">
                        Tick a question type to see how it is graded.
                      </li>
                    ) : null}
                  </ul>
                ) : null}
              </div>
            </CardContent>
          </>
        )}

        <div className="flex items-center gap-3 border-t px-6 py-4">
          <Button variant="outline" size="sm" disabled={step === 0} onClick={() => setStep(0)}>
            <ArrowLeftIcon />
            Back
          </Button>
          <span className="text-muted-foreground text-sm">
            {step === 0
              ? preset
                ? `${types.size} question types ticked`
                : "Pick a subject to continue."
              : `${types.size} question types`}
          </span>
          <div className="ml-auto flex items-center gap-3">
            {submitted ? (
              <span className="flex items-center gap-1.5 text-muted-foreground text-sm">
                <InfoIcon className="size-4" />
                Prototype — nothing is saved.
              </span>
            ) : null}
            {step === 0 ? (
              <Button size="sm" disabled={!preset} onClick={() => setStep(1)}>
                Next
                <ArrowRightIcon />
              </Button>
            ) : (
              <Button
                size="sm"
                disabled={types.size === 0}
                // TODO(real): POST the course with its name, subject and the derived capability ids.
                onClick={() => setSubmitted(true)}
              >
                Create course
              </Button>
            )}
          </div>
        </div>
      </Card>
    </div>
  );
}
