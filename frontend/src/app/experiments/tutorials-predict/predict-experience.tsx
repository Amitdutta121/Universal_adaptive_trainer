"use client";

/**
 * Variant E of the student tutorial prototypes: "Predict, then reveal". Three predict-then-reveal
 * experiments, a free-play box, and a recap of only the predictions the student got wrong. Mock
 * data only (see `mock-data.ts`); nothing here calls the API and progress is not persisted.
 *
 * TODO(real): experiments come from the book section and are approved by the professor; whether
 * this variant is offered at all follows the student's practice results (2 of 3 for-loop
 * questions wrong).
 */

import { FlaskConical, Home } from "lucide-react";
import { useState } from "react";
import { Progress } from "@/components/ui/progress";
import { ExperimentStep } from "./components/experiment-step";
import { FreePlay } from "./components/free-play";
import { Recap } from "./components/recap";
import { type Answer, EXPERIMENTS, surprises, TOTAL_STEPS } from "./mock-data";

export function PredictExperience() {
  /** 0..2 are the experiments, 3 is free play, 4 is the recap. */
  const [step, setStep] = useState(0);
  const [answers, setAnswers] = useState<Record<string, Answer>>({});
  /** Focus follows the step only after the student has moved once; the page opens with no focus grab. */
  const [moved, setMoved] = useState(false);

  const experiment = EXPERIMENTS[step];
  const answered = Object.keys(answers).length;
  const wrong = surprises(answers);
  const inRecap = step >= TOTAL_STEPS;

  function goTo(next: number) {
    setMoved(true);
    setStep(next);
  }

  return (
    <div className="min-h-screen bg-background text-foreground">
      <header className="border-border border-b bg-card/60">
        <div className="mx-auto flex max-w-5xl flex-wrap items-center justify-between gap-3 px-4 py-3 sm:px-6">
          <div className="flex items-center gap-2.5">
            <span className="flex size-8 items-center justify-center rounded-lg bg-primary text-primary-foreground">
              <FlaskConical className="size-4" aria-hidden="true" />
            </span>
            <div>
              <p className="font-mono text-[0.68rem] text-muted-foreground uppercase tracking-widest">
                Design prototype
              </p>
              <h1 className="font-heading font-semibold text-foreground text-sm">
                Tutorial E: predict, then reveal
              </h1>
            </div>
          </div>
          <a
            href="/dashboard"
            className="inline-flex items-center gap-1.5 rounded-md border border-border px-2.5 py-1.5 text-muted-foreground text-sm outline-none hover:text-foreground focus-visible:ring-3 focus-visible:ring-ring/50"
          >
            <Home className="size-3.5" aria-hidden="true" />
            Dashboard
          </a>
        </div>
      </header>

      <div className="mx-auto max-w-5xl px-4 py-3 sm:px-6">
        <p className="rounded-lg border border-amber-500/30 bg-amber-500/10 px-3 py-2 text-amber-800 text-sm dark:text-amber-200">
          <strong className="font-medium">Prototype.</strong> Mock data: these experiments are
          hand-written. Real ones are generated from the book section and approved by the professor.
        </p>
      </div>

      <main className="mx-auto w-full max-w-xl px-4 py-6 sm:px-6 sm:py-10">
        {inRecap ? null : (
          <div className="mb-6 grid gap-2">
            <div className="flex items-center justify-between font-mono text-muted-foreground text-xs">
              <span>
                Experiment {step + 1} of {TOTAL_STEPS}
              </span>
              {answered > 0 ? <span>Surprises: {wrong.length}</span> : null}
            </div>
            <Progress
              value={(step / TOTAL_STEPS) * 100}
              aria-label="Experiments finished"
              className="h-1.5"
            />
          </div>
        )}

        {inRecap ? (
          <Recap
            wrong={wrong}
            answers={answers}
            onRestart={() => {
              setAnswers({});
              setStep(0);
            }}
          />
        ) : experiment ? (
          <ExperimentStep
            key={experiment.id}
            experiment={experiment}
            answer={answers[experiment.id]}
            onAnswer={(answer) => setAnswers((current) => ({ ...current, [experiment.id]: answer }))}
            onNext={() => goTo(step + 1)}
            nextLabel={step === EXPERIMENTS.length - 1 ? "Try your own" : "Next"}
            focusHeading={moved}
          />
        ) : (
          <FreePlay onFinish={() => goTo(step + 1)} focusHeading={moved} />
        )}
      </main>
    </div>
  );
}
