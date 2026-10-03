"use client";

/**
 * Step 1 · Read the book. Plays back the mining run (table of contents -> practice sections ->
 * exercises -> analysis -> suggestions), then shows what was found.
 * TODO(real): poll the mining job; each stage is one row of its status.
 */

import { BookOpenIcon, CheckIcon, LoaderCircleIcon } from "lucide-react";
import { useEffect, useState } from "react";
import { Progress } from "@/components/ui/progress";
import { cn } from "@/lib/utils";
import { DIFFICULTIES, DIFFICULTY_LABEL, type Domain, type MinedSection } from "../mock-types";
import { DifficultyBadge } from "./badges";

const STAGE_MS = 850;

const KIND_LABEL: Record<MinedSection["kind"], string> = {
  exercises: "Practice problems",
  conceptual: "Conceptual questions",
  review: "Review questions",
  objectives: "Objectives and terms",
  answers: "Answer key",
};

function stagesFor(domain: Domain) {
  const routedRegex = domain.mining.sections.reduce((sum, section) => sum + section.count, 0);
  return [
    {
      title: "Reading the table of contents",
      detail: `${domain.book.sections} sections · ${domain.mining.tocTokens.toLocaleString()} tokens, one call`,
    },
    {
      title: "Finding practice sections",
      detail: `${routedRegex} sections hold exercises, reviews or objectives`,
    },
    {
      title: "Pulling out exercises",
      detail: `${domain.mining.itemsFound} items found`,
    },
    {
      title: "Labelling type and difficulty",
      detail: `Level: ${domain.mining.level}`,
    },
    {
      title: "Drafting question styles for your course",
      detail: `${domain.templates.length} styles using ${Object.keys(domain.questionTypes).length} question types`,
    },
  ];
}

export function StepMining({
  domain,
  done,
  onDone,
  wishes,
  onToggleWish,
}: {
  domain: Domain;
  done: boolean;
  onDone(): void;
  wishes: ReadonlySet<string>;
  onToggleWish(wish: string): void;
}) {
  const stages = stagesFor(domain);
  const [current, setCurrent] = useState(done ? stages.length : 0);

  useEffect(() => {
    if (current >= stages.length) {
      if (!done) onDone();
      return;
    }
    const timer = window.setTimeout(() => setCurrent((value) => value + 1), STAGE_MS);
    return () => window.clearTimeout(timer);
  }, [current, stages.length, done, onDone]);

  const finished = current >= stages.length;
  const mining = domain.mining;
  const totalMix = DIFFICULTIES.reduce((sum, d) => sum + mining.difficultyMix[d], 0);

  return (
    <div className="flex flex-col gap-6">
      <div className="flex items-start gap-3 rounded-lg border bg-muted/30 p-3.5">
        <BookOpenIcon className="mt-0.5 size-5 shrink-0 text-muted-foreground" aria-hidden />
        <div className="min-w-0 text-sm">
          <p className="font-medium">{domain.book.title}</p>
          <p className="text-muted-foreground">
            {domain.book.author} · {domain.book.pages} pages · {domain.book.chapters} chapters ·{" "}
            {domain.book.sections} sections
          </p>
        </div>
      </div>

      <section aria-labelledby="mining-progress" className="flex flex-col gap-3">
        <div className="flex items-center justify-between gap-3">
          <h3 id="mining-progress" className="font-medium text-sm">
            {finished ? "Finished reading the book" : "Reading the book…"}
          </h3>
          <span className="text-muted-foreground text-xs tabular-nums">
            {Math.min(current, stages.length)} / {stages.length}
          </span>
        </div>
        <Progress value={(Math.min(current, stages.length) / stages.length) * 100} />
        <ol className="flex flex-col gap-2" aria-live="polite">
          {stages.map((stage, index) => {
            const state = index < current ? "done" : index === current ? "running" : "waiting";
            return (
              <li key={stage.title} className="flex items-start gap-3 text-sm">
                <span className="mt-0.5 flex size-4 shrink-0 items-center justify-center">
                  {state === "done" ? (
                    <CheckIcon className="size-4 text-[var(--ok-solid)]" aria-label="Done" />
                  ) : state === "running" ? (
                    <LoaderCircleIcon className="size-4 animate-spin text-muted-foreground" aria-label="Running" />
                  ) : (
                    <><span aria-hidden className="size-1.5 rounded-full bg-border" /><span className="sr-only">Waiting</span></>
                  )}
                </span>
                <span className={cn("flex-1", state === "waiting" && "text-muted-foreground")}>
                  {stage.title}
                  {state === "done" ? (
                    <span className="block text-muted-foreground text-xs">{stage.detail}</span>
                  ) : null}
                </span>
              </li>
            );
          })}
        </ol>
      </section>

      {finished ? (
        <>
          <section aria-labelledby="found" className="grid gap-5 md:grid-cols-2">
            <div className="flex flex-col gap-2">
              <h3 id="found" className="font-medium text-sm">
                Sections used
              </h3>
              <table className="w-full text-sm">
                <tbody>
                  {mining.sections.map((section) => (
                    <tr key={section.title} className="border-b last:border-0">
                      <td className="py-1.5 pr-3">{section.title}</td>
                      <td className="py-1.5 pr-3 text-muted-foreground text-xs">{KIND_LABEL[section.kind]}</td>
                      <td className="py-1.5 text-right tabular-nums">×{section.count}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
            <div className="flex flex-col gap-2">
              <h3 className="font-medium text-sm">What the {mining.itemsFound} items ask</h3>
              <ul className="flex flex-col gap-1.5">
                {mining.taskMix.map((entry) => (
                  <li key={entry.label} className="grid grid-cols-[1fr_auto] items-center gap-x-3 text-sm">
                    <span>{entry.label}</span>
                    <span className="text-muted-foreground text-xs tabular-nums">
                      {Math.round(entry.share * 100)}%
                    </span>
                    <span className="col-span-2 h-1 overflow-hidden rounded-full bg-muted">
                      <span
                        className="block h-full bg-[var(--accent-solid)]"
                        style={{ width: `${entry.share * 100}%` }}
                      />
                    </span>
                  </li>
                ))}
              </ul>
              <p className="text-muted-foreground text-xs">
                Difficulty:{" "}
                {DIFFICULTIES.map(
                  (d) =>
                    `${DIFFICULTY_LABEL[d].toLowerCase()} ${Math.round((mining.difficultyMix[d] / totalMix) * 100)}%`,
                ).join(" · ")}
              </p>
            </div>
          </section>

          <section aria-labelledby="samples" className="flex flex-col gap-2">
            <h3 id="samples" className="font-medium text-sm">
              Examples from the book
            </h3>
            <ul className="divide-y rounded-lg border">
              {mining.samples.map((sample) => (
                <li key={sample.text} className="flex flex-col gap-1 px-3 py-2.5 sm:flex-row sm:items-start sm:gap-4">
                  <p className="flex-1 text-sm">{sample.text}</p>
                  <div className="flex shrink-0 flex-wrap items-center gap-2 text-muted-foreground text-xs">
                    <span>{sample.source}</span>
                    <span aria-hidden>·</span>
                    <span>{sample.inferredType}</span>
                    <DifficultyBadge difficulty={sample.difficulty} />
                  </div>
                </li>
              ))}
            </ul>
            <ul className="flex flex-col gap-1 text-muted-foreground text-xs">
              {mining.notes.map((note) => (
                <li key={note}>{note}</li>
              ))}
            </ul>
          </section>

          <section aria-labelledby="wishes" className="flex flex-col gap-2 border-t pt-5">
            <h3 id="wishes" className="font-medium text-sm">
              Anything you want more or less of? <span className="font-normal text-muted-foreground">Optional</span>
            </h3>
            <div className="flex flex-wrap gap-2">
              {domain.wishes.map((wish) => {
                const on = wishes.has(wish);
                return (
                  <button
                    key={wish}
                    type="button"
                    aria-pressed={on}
                    onClick={() => onToggleWish(wish)}
                    className={cn(
                      "rounded-full border px-3 py-1 text-sm outline-none transition-colors focus-visible:ring-3 focus-visible:ring-ring/50",
                      on
                        ? "border-[var(--accent-solid)] bg-[var(--accent-wash)] text-[var(--accent-text)]"
                        : "hover:bg-muted",
                    )}
                  >
                    {on ? <CheckIcon className="mr-1 -ml-0.5 inline size-3.5" aria-hidden /> : null}
                    {wish}
                  </button>
                );
              })}
            </div>
          </section>
        </>
      ) : null}
    </div>
  );
}
