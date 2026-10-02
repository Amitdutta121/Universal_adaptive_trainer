"use client";

/**
 * Variant C of the student tutorials: no tutorial page. Help appears where the student is stuck.
 *
 * Flow (2 clicks from a wrong answer back to practice): pick a wrong option -> one-line reason under
 * the question -> optional "Need a refresher?" bottom sheet -> "Got it, try another". The second time
 * the same misconception is picked, the sheet says so and offers the fuller 6-line version.
 *
 * Mock data only (see `mock-data.ts`); nothing here calls a server or a model.
 */

import { ArrowRight, FlaskConical, Home } from "lucide-react";
import { useEffect, useRef, useState } from "react";
import { Button } from "@/components/ui/button";
import { QuestionCard } from "./components/question-card";
import { RefresherSheet } from "./components/refresher-sheet";
import { type MisconceptionId, QUESTIONS, REFRESHERS } from "./mock-data";

type Counts = Partial<Record<MisconceptionId, number>>;

export function TutorialsInlineExperience() {
  const [index, setIndex] = useState(0);
  const [pickedId, setPickedId] = useState<string | null>(null);
  const [submitted, setSubmitted] = useState(false);
  const [sheetOpen, setSheetOpen] = useState(false);
  const [counts, setCounts] = useState<Counts>({});
  const [correctCount, setCorrectCount] = useState(0);

  const headingRef = useRef<HTMLHeadingElement>(null);
  const resultRef = useRef<HTMLDivElement>(null);
  const doneRef = useRef<HTMLHeadingElement>(null);
  // Focus is moved only after a user action, never on first paint.
  const focusAfterRender = useRef<"result" | "question" | null>(null);

  const done = index >= QUESTIONS.length;
  const question = done ? null : QUESTIONS[index];
  const picked = question?.options.find((option) => option.id === pickedId);
  const isLastQuestion = index === QUESTIONS.length - 1;

  // biome-ignore lint/correctness/useExhaustiveDependencies: re-run after every state change that can request focus
  useEffect(() => {
    const target = focusAfterRender.current;
    if (!target) return;
    focusAfterRender.current = null;
    if (target === "result") resultRef.current?.focus();
    else (headingRef.current ?? doneRef.current)?.focus();
  }, [index, submitted]);

  const submit = () => {
    if (!picked) return;
    if (picked.correct) setCorrectCount((n) => n + 1);
    else if (picked.misconception) {
      const id = picked.misconception;
      setCounts((prev) => ({ ...prev, [id]: (prev[id] ?? 0) + 1 }));
    }
    focusAfterRender.current = "result";
    setSubmitted(true);
  };

  const next = () => {
    focusAfterRender.current = "question";
    setSheetOpen(false);
    setPickedId(null);
    setSubmitted(false);
    setIndex((i) => i + 1);
  };

  const restart = () => {
    focusAfterRender.current = "question";
    setCounts({});
    setCorrectCount(0);
    setPickedId(null);
    setSubmitted(false);
    setIndex(0);
  };

  const misconception = picked && !picked.correct ? picked.misconception : undefined;
  const openMisconceptions = (Object.entries(counts) as [MisconceptionId, number][]).filter(
    ([, count]) => count > 0,
  );

  return (
    <div className="min-h-screen bg-background text-foreground">
      <header className="border-border border-b bg-card/60">
        <div className="mx-auto flex max-w-3xl flex-wrap items-center justify-between gap-3 px-4 py-3 sm:px-6">
          <div className="flex items-center gap-2.5">
            <span className="flex size-8 items-center justify-center rounded-lg bg-primary text-primary-foreground">
              <FlaskConical className="size-4" aria-hidden="true" />
            </span>
            <span>
              <span className="block font-mono text-[0.68rem] text-muted-foreground uppercase tracking-widest">
                Design prototype
              </span>
              <span className="block font-heading font-semibold text-foreground text-sm">
                Tutorial C: help inside the question
              </span>
            </span>
          </div>
          <a
            href="/dashboard"
            className="inline-flex items-center gap-1.5 rounded-md border border-border px-2.5 py-1.5 text-muted-foreground text-sm hover:text-foreground"
          >
            <Home className="size-3.5" aria-hidden="true" />
            Console
          </a>
        </div>
      </header>

      <div className="mx-auto max-w-3xl px-4 py-3 sm:px-6">
        <p className="rounded-lg border border-amber-500/30 bg-amber-500/10 px-3 py-2 text-amber-800 text-sm dark:text-amber-200">
          <strong className="font-medium">Prototype.</strong> Mock data: three hand-written questions,
          misconception tags and refreshers. Nothing here calls a server or a model.
        </p>
      </div>

      <main className="mx-auto max-w-3xl px-4 pb-16 sm:px-6">
        {question ? (
          <QuestionCard
            // Remount per question so radio state and focus start clean.
            key={question.id}
            question={question}
            index={index}
            total={QUESTIONS.length}
            pickedId={pickedId}
            onPick={setPickedId}
            submitted={submitted}
            onSubmit={submit}
            headingRef={headingRef}
            resultRef={resultRef}
            actions={
              <>
                {misconception ? (
                  <RefresherSheet
                    open={sheetOpen}
                    onOpenChange={setSheetOpen}
                    refresher={REFRESHERS[misconception]}
                    count={counts[misconception] ?? 1}
                    isLastQuestion={isLastQuestion}
                    onGotIt={next}
                  />
                ) : null}
                <Button
                  type="button"
                  variant={misconception ? "ghost" : "default"}
                  onClick={next}
                >
                  {isLastQuestion ? "See summary" : "Next question"}
                  <ArrowRight />
                </Button>
              </>
            }
          />
        ) : (
          <section
            aria-labelledby="done-heading"
            className="space-y-4 rounded-xl border border-border bg-card p-5 ring-1 ring-foreground/5 sm:p-6"
          >
            <h2
              id="done-heading"
              ref={doneRef}
              tabIndex={-1}
              className="rounded-sm font-heading font-semibold text-foreground text-xl tracking-tight outline-none focus-visible:ring-2 focus-visible:ring-ring"
            >
              Set finished
            </h2>
            <p className="text-foreground text-sm leading-6">
              {correctCount} of {QUESTIONS.length} correct.
            </p>
            {openMisconceptions.length > 0 ? (
              <ul className="space-y-1 text-muted-foreground text-sm">
                {openMisconceptions.map(([id, count]) => (
                  <li key={id}>
                    {REFRESHERS[id].title}: picked {count} {count === 1 ? "time" : "times"}
                  </li>
                ))}
              </ul>
            ) : null}
            <Button type="button" onClick={restart}>
              Start over
            </Button>
          </section>
        )}
      </main>
    </div>
  );
}
