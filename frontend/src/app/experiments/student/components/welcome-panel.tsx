"use client";

import { ArrowRight, RotateCcw, Sparkles, Target, TrendingUp } from "lucide-react";
import { useId, useState } from "react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { cn } from "@/lib/utils";
import { PRACTICE_SETS } from "../mock-data";

export function WelcomePanel({
  defaultName,
  defaultSetId,
  hasSavedSession,
  savedSummary,
  onResume,
  onStart,
}: {
  defaultName: string;
  defaultSetId: string;
  hasSavedSession: boolean;
  savedSummary: string | null;
  onResume: () => void;
  onStart: (setId: string, name: string) => void;
}) {
  const nameId = useId();
  const [name, setName] = useState(defaultName);
  const [setId, setSetId] = useState(defaultSetId);

  return (
    <div className="space-y-6">
      <header className="space-y-3">
        <h1 className="font-heading font-semibold text-3xl text-foreground tracking-tight">
          Practice Python, paced to you
        </h1>
        <p className="max-w-prose text-muted-foreground leading-7">
          Answer one question at a time. Each answer is scored right away, and the next question is
          chosen from the subtopics you're weakest in — so the set works on what you actually need.
        </p>
      </header>

      {hasSavedSession ? (
        <div className="flex flex-col gap-3 rounded-xl border border-primary/40 bg-primary/5 p-4 sm:flex-row sm:items-center sm:justify-between">
          <div>
            <p className="font-medium text-foreground text-sm">
              You have a practice run in progress
            </p>
            {savedSummary ? <p className="text-muted-foreground text-sm">{savedSummary}</p> : null}
          </div>
          <Button type="button" onClick={onResume} className="w-full shrink-0 sm:w-auto">
            <RotateCcw />
            Resume
          </Button>
        </div>
      ) : null}

      <form
        className="space-y-4 rounded-xl border border-border bg-card p-5 ring-1 ring-foreground/5 sm:p-6"
        onSubmit={(event) => {
          event.preventDefault();
          onStart(setId, name.trim());
        }}
      >
        <div className="grid gap-3 border-border border-b pb-4 sm:grid-cols-3">
          <div className="flex items-start gap-2.5">
            <Target className="mt-0.5 size-4 shrink-0 text-primary" aria-hidden="true" />
            <span className="text-foreground text-sm leading-6">
              Questions favor the subtopics you're weakest in.
            </span>
          </div>
          <div className="flex items-start gap-2.5">
            <TrendingUp className="mt-0.5 size-4 shrink-0 text-primary" aria-hidden="true" />
            <span className="text-foreground text-sm leading-6">
              Difficulty follows your measured mastery, topic by topic.
            </span>
          </div>
          <div className="flex items-start gap-2.5">
            <Sparkles className="mt-0.5 size-4 shrink-0 text-primary" aria-hidden="true" />
            <span className="text-foreground text-sm leading-6">
              Your progress is saved on this device as you go.
            </span>
          </div>
        </div>

        <div className="space-y-2">
          <label className="font-medium text-foreground text-sm" htmlFor={nameId}>
            Your name <span className="font-normal text-muted-foreground">(optional)</span>
          </label>
          <Input
            id={nameId}
            value={name}
            onChange={(event) => setName(event.target.value)}
            maxLength={80}
            placeholder="e.g. Ada"
            className="max-w-sm"
            autoComplete="given-name"
          />
        </div>

        <fieldset className="space-y-2">
          <legend className="mb-1 font-medium text-foreground text-sm">
            Choose a practice set
          </legend>
          {PRACTICE_SETS.map((set) => (
            <label
              key={set.id}
              className={cn(
                "flex cursor-pointer items-start gap-3 rounded-lg border p-3 transition-colors",
                setId === set.id
                  ? "border-primary bg-primary/5"
                  : "border-border bg-card hover:bg-muted/50",
              )}
            >
              <input
                type="radio"
                name="practice-set"
                value={set.id}
                checked={setId === set.id}
                onChange={() => setSetId(set.id)}
                className="mt-0.5 size-4 accent-[var(--primary)]"
              />
              <span className="space-y-0.5">
                <span className="block font-medium text-foreground text-sm">{set.label}</span>
                <span className="block text-muted-foreground text-sm">{set.blurb}</span>
                <span className="block text-muted-foreground text-xs">
                  {set.questionIds.length} questions
                </span>
              </span>
            </label>
          ))}
        </fieldset>

        <Button type="submit" size="lg" className="w-full sm:w-auto">
          <ArrowRight />
          Start practising
        </Button>
      </form>
    </div>
  );
}
