"use client";

import { useState } from "react";
import { Badge } from "@/components/ui/badge";
import { cn } from "@/lib/utils";
import { MOCK_PROMPTS, type MockPrompt, SUBJECTS } from "./mock-prompts";
import { PromptText } from "@/components/prompt-text";

type Mode = "rendered" | "raw";

export function PromptTextExperience() {
  const [subject, setSubject] = useState<string>("All");
  const [mode, setMode] = useState<Mode>("rendered");
  const rows = MOCK_PROMPTS.filter((row) => subject === "All" || row.subject === subject);

  return (
    <main className="min-h-screen bg-background">
      <div className="mx-auto max-w-3xl space-y-8 px-5 py-10">
        <header className="space-y-2">
          <h1 className="font-semibold text-2xl text-foreground">PromptText</h1>
          <p className="max-w-2xl text-muted-foreground text-sm">
            One component for every place a question prompt is shown. Rows marked{" "}
            <em>stored</em> are copied from the dev database; the rest are written to the proposed
            generator rules. Switch to <em>Today</em> to see the same strings as plain text.
          </p>
        </header>

        <div className="flex flex-wrap items-center justify-between gap-3">
          <div className="flex flex-wrap gap-1.5">
            {["All", ...SUBJECTS].map((name) => (
              <button
                key={name}
                type="button"
                onClick={() => setSubject(name)}
                className={cn(
                  "rounded-full border px-3 py-1 text-sm transition-colors",
                  subject === name
                    ? "border-primary bg-primary text-primary-foreground"
                    : "border-border bg-card text-foreground hover:bg-muted",
                )}
              >
                {name}
              </button>
            ))}
          </div>
          <div className="inline-flex rounded-lg border border-border bg-card p-0.5 text-sm">
            {(["rendered", "raw"] as const).map((value) => (
              <button
                key={value}
                type="button"
                onClick={() => setMode(value)}
                className={cn(
                  "rounded-md px-3 py-1",
                  mode === value ? "bg-muted font-medium text-foreground" : "text-muted-foreground",
                )}
              >
                {value === "rendered" ? "With PromptText" : "Today"}
              </button>
            ))}
          </div>
        </div>

        <section className="space-y-4">
          <h2 className="font-medium text-foreground text-sm">Student question panel</h2>
          {rows.map((row) => (
            <QuestionCard key={row.id} row={row} mode={mode} />
          ))}
        </section>

        <section className="space-y-3">
          <h2 className="font-medium text-foreground text-sm">Questions table (preview rows)</h2>
          <div className="overflow-hidden rounded-lg border border-border bg-card">
            {rows.map((row) => (
              <div
                key={row.id}
                className="grid grid-cols-[9rem_1fr] gap-3 border-border border-t px-4 py-2.5 first:border-t-0"
              >
                <div className="text-muted-foreground text-xs leading-5">
                  <div className="text-foreground">{row.type}</div>
                  {row.subject}
                </div>
                {mode === "rendered" ? (
                  <PromptText text={row.prompt} variant="preview" />
                ) : (
                  <span className="line-clamp-2 text-[0.8rem] leading-5">{row.prompt}</span>
                )}
              </div>
            ))}
          </div>
        </section>
      </div>
    </main>
  );
}

function QuestionCard({ row, mode }: { row: MockPrompt; mode: Mode }) {
  return (
    <article className="space-y-4 rounded-xl border border-border bg-card p-5">
      <header className="flex flex-wrap items-center gap-2">
        <Badge variant="outline">{row.type}</Badge>
        <span className="text-muted-foreground text-sm">{row.subject}</span>
        {row.source === "stored" ? (
          <span className="ml-auto text-muted-foreground text-xs">stored</span>
        ) : null}
      </header>

      <div className="rounded-lg border border-border bg-background/60 p-4">
        {mode === "rendered" ? (
          <PromptText text={row.prompt} />
        ) : (
          <div className="whitespace-pre-wrap text-foreground leading-7">{row.prompt}</div>
        )}
      </div>

      {row.options ? (
        <fieldset className="space-y-2">
          <legend className="mb-1 font-medium text-foreground text-sm">Choose one answer</legend>
          {row.options.map((option) => (
            <div
              key={option}
              className="flex items-start gap-3 rounded-lg border border-border bg-card p-3 text-sm"
            >
              <span className="mt-1 size-3.5 shrink-0 rounded-full border border-border" />
              {mode === "rendered" ? (
                <PromptText text={option} className="leading-6" />
              ) : (
                <span>{option}</span>
              )}
            </div>
          ))}
        </fieldset>
      ) : null}
    </article>
  );
}
