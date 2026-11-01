"use client";

/**
 * Variant G of the student tutorials: practice first, simulator on demand. There is no tutorial
 * page: the practice screen IS the tutorial, and help is a ladder that opens only when the student
 * asks or misses.
 *
 *   Rung 1  one line naming the misconception (never the answer); the student gets ONE more attempt.
 *   Rung 2  "Show me what happens": a step-through simulator of the question's own code, with the
 *           student's answer pinned next to the real output. Offered after a miss, prominent after
 *           the second miss, and available on demand after a correct answer too.
 *   Rung 3  "Explain it like a worked example": a short worked example, then a faded one whose last
 *           line the student completes, then "Try another".
 *
 * Nothing is forced and nothing plays by itself. Adaptivity is a stub: two misses on a topic bring
 * the next question from that topic (`practice-logic.ts`).
 *
 * Mock data only (see `mock-data.ts`); nothing here calls a server or a model.
 */

import { ArrowRight, FlaskConical, Home } from "lucide-react";
import { type ReactNode, useEffect, useRef, useState } from "react";
import { Button } from "@/components/ui/button";
import { ChoiceQuestion } from "./components/choice-question";
import { Inline } from "./components/code-view";
import { ParsonsQuestion } from "./components/parsons-question";
import { type Pinned, SimulatorSheet } from "./components/simulator-sheet";
import { TopicStrip } from "./components/topic-strip";
import { WorkedExample } from "./components/worked-example";
import {
  BANK,
  type ChoiceOption,
  MISCONCEPTIONS,
  type MisconceptionId,
  type Question,
  topicLabel,
} from "./mock-data";
import {
  checkParsons,
  correctOption,
  initialStats,
  type Outcome,
  optionMatches,
  parsonsCode,
  parsonsSolution,
  pickNext,
  recordCorrect,
  recordMiss,
  recordOutcome,
  type Stats,
} from "./practice-logic";

interface AttemptRecord {
  misconception: MisconceptionId | null;
  /** What the student answered (choice text, or the goal for an ordering). */
  text: string;
  /** The program that answer produces; the simulator runs this. */
  code: string;
  option?: ChoiceOption;
}

interface Attempt {
  wrong: AttemptRecord[];
  outcome: "open" | Outcome;
  correct: AttemptRecord | null;
  workedOpen: boolean;
  sheetSeen: boolean;
}

const FRESH_ATTEMPT: Attempt = {
  wrong: [],
  outcome: "open",
  correct: null,
  workedOpen: false,
  sheetSeen: false,
};

const startOrder = (question: Question): string[] =>
  question.kind === "parsons" ? [...question.start] : [];

export function TutorialsPracticeExperience() {
  const [stats, setStats] = useState<Stats>(initialStats);
  const [answered, setAnswered] = useState<string[]>([]);
  const [question, setQuestion] = useState<Question>(BANK[0]);
  const [steerNote, setSteerNote] = useState<string | null>(null);
  const [attempt, setAttempt] = useState<Attempt>(FRESH_ATTEMPT);
  const [pickedId, setPickedId] = useState<string | null>(null);
  const [order, setOrder] = useState<string[]>(() => startOrder(BANK[0]));
  const [sheetOpen, setSheetOpen] = useState(false);
  const [done, setDone] = useState(false);

  const headingRef = useRef<HTMLHeadingElement>(null);
  const feedbackRef = useRef<HTMLDivElement>(null);
  const doneRef = useRef<HTMLHeadingElement>(null);
  const workedHeadingRef = useRef<HTMLHeadingElement>(null);
  // Focus moves only after a user action, never on first paint.
  const focusAfterRender = useRef<"feedback" | "question" | null>(null);
  const focusWorked = useRef(false);

  // biome-ignore lint/correctness/useExhaustiveDependencies: re-run after every state change that can request focus
  useEffect(() => {
    const target = focusAfterRender.current;
    if (!target) return;
    focusAfterRender.current = null;
    if (target === "feedback") feedbackRef.current?.focus();
    else (headingRef.current ?? doneRef.current)?.focus();
  }, [attempt, question, done]);

  const finished = attempt.outcome !== "open";
  const lastWrong = attempt.wrong[attempt.wrong.length - 1];
  const lastAnswer = attempt.correct ?? lastWrong;
  const upcoming = pickNext([...answered, question.id], stats);

  // ---- actions ----------------------------------------------------------------------------

  const finish = (nextAttempt: Attempt) => {
    focusAfterRender.current = "feedback";
    setAttempt(nextAttempt);
  };

  /** A right or wrong attempt has been judged: update the attempt, the stats and the dots. */
  const judge = (record: AttemptRecord) => {
    const wrongSoFar = attempt.wrong.length;
    if (record.misconception === null) {
      const outcome: Outcome = wrongSoFar === 0 ? "right" : "recovered";
      setStats((s) => recordOutcome(recordCorrect(s, question.topic), question.topic, outcome));
      finish({ ...attempt, outcome, correct: record });
      return;
    }
    const wrong = [...attempt.wrong, record];
    const missed = wrong.length >= 2;
    setStats((s) => {
      const next = recordMiss(s, question.topic);
      return missed ? recordOutcome(next, question.topic, "missed") : next;
    });
    if (missed && question.kind === "parsons") setOrder(parsonsSolution(question));
    setPickedId(null);
    finish({ ...attempt, wrong, outcome: missed ? "missed" : "open" });
  };

  const submit = () => {
    if (question.kind === "choice") {
      const option = question.options.find((o) => o.id === pickedId);
      if (!option) return;
      judge({
        misconception: option.misconception,
        text: option.text,
        code: question.code,
        option,
      });
      return;
    }
    const check = checkParsons(question, order);
    judge({
      misconception: check.misconception,
      text: question.expected.trim(),
      code: parsonsCode(question, order),
    });
  };

  const next = () => {
    setSheetOpen(false);
    focusAfterRender.current = "question";
    const pick = pickNext([...answered, question.id], stats);
    setAnswered((a) => [...a, question.id]);
    setAttempt(FRESH_ATTEMPT);
    setPickedId(null);
    if (!pick) {
      setDone(true);
      return;
    }
    setQuestion(pick.question);
    setOrder(startOrder(pick.question));
    setSteerNote(
      pick.reason === "steered"
        ? `More on ${topicLabel(pick.question.topic).toLowerCase()}, since the last two answers missed.`
        : null,
    );
  };

  const restart = () => {
    focusAfterRender.current = "question";
    setStats(initialStats());
    setAnswered([]);
    setQuestion(BANK[0]);
    setOrder(startOrder(BANK[0]));
    setAttempt(FRESH_ATTEMPT);
    setPickedId(null);
    setSteerNote(null);
    setDone(false);
  };

  const openSheet = (open: boolean) => {
    setSheetOpen(open);
    if (open) setAttempt((a) => ({ ...a, sheetSeen: true }));
  };

  const explain = () => {
    focusWorked.current = true;
    setSheetOpen(false);
    setAttempt((a) => ({ ...a, workedOpen: true }));
  };

  const showWorked = () => {
    focusWorked.current = true;
    setAttempt((a) => ({ ...a, workedOpen: true }));
    // The heading is not mounted yet in this render; the effect below focuses it.
    requestAnimationFrame(() => {
      if (focusWorked.current) {
        focusWorked.current = false;
        workedHeadingRef.current?.focus();
      }
    });
  };

  // ---- simulator input ---------------------------------------------------------------------

  const pinned: Pinned | null = (() => {
    if (!lastAnswer) return null;
    if (question.kind === "parsons") {
      return {
        label: "You wanted",
        text: question.expected.trim(),
        actualLabel: "Your order prints",
        matches: (r) => r.status === "ok" && r.output === question.expected,
      };
    }
    const option = lastAnswer.option;
    return {
      label: "Your answer",
      text: lastAnswer.text,
      actualLabel: "Actual output",
      matches: (r) => (option ? optionMatches(option, r) : false),
    };
  })();

  const misconception = lastWrong?.misconception ? MISCONCEPTIONS[lastWrong.misconception] : null;

  // ---- render -------------------------------------------------------------------------------

  const summary = {
    right: countOutcome(stats, "right"),
    recovered: countOutcome(stats, "recovered"),
    missed: countOutcome(stats, "missed"),
  };

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
                Tutorial G: practice first
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
          <strong className="font-medium">Prototype.</strong> Mock data: ten hand-written questions,
          misconception tags and examples. The step-through runs a small Python subset in the
          browser, not CPython. Nothing here calls a server or a model.
        </p>
      </div>

      <main className="mx-auto max-w-3xl space-y-4 px-4 pb-16 sm:px-6">
        <TopicStrip stats={stats} />

        {done ? (
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
              {summary.right} right first time, {summary.recovered} on the second try,{" "}
              {summary.missed} missed.
            </p>
            <Button type="button" onClick={restart}>
              Start over
            </Button>
          </section>
        ) : (
          <section
            // Remount per question so radio state and focus start clean.
            key={question.id}
            aria-labelledby="question-heading"
            className="space-y-4 rounded-xl border border-border bg-card p-5 ring-1 ring-foreground/5 sm:p-6"
          >
            <header className="space-y-1">
              <div className="flex flex-wrap items-baseline gap-x-3 gap-y-1">
                <h2
                  id="question-heading"
                  ref={headingRef}
                  tabIndex={-1}
                  className="rounded-sm font-heading font-semibold text-foreground text-xl tracking-tight outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2 focus-visible:ring-offset-background"
                >
                  Question {answered.length + 1} of {BANK.length}
                </h2>
                <span className="text-muted-foreground text-sm">{topicLabel(question.topic)}</span>
              </div>
              {steerNote ? <p className="text-muted-foreground text-xs">{steerNote}</p> : null}
            </header>

            {question.kind === "choice" ? (
              <ChoiceQuestion
                question={question}
                pickedId={pickedId}
                onPick={setPickedId}
                wrongIds={attempt.wrong.flatMap((w) => (w.option ? [w.option.id] : []))}
                finished={finished}
                correctId={correctOption(question).id}
              />
            ) : (
              <ParsonsQuestion
                question={question}
                order={order}
                onOrder={setOrder}
                locked={finished}
              />
            )}

            {finished ? null : (
              <Button
                type="button"
                size="lg"
                onClick={submit}
                disabled={question.kind === "choice" && !pickedId}
                className="w-full sm:w-auto"
              >
                {question.kind === "choice" ? "Check answer" : "Check order"}
                <ArrowRight aria-hidden="true" />
              </Button>
            )}

            <div
              ref={feedbackRef}
              tabIndex={-1}
              role="status"
              aria-live="polite"
              className="rounded-lg outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2 focus-visible:ring-offset-background"
            >
              {attempt.outcome === "right" ? <Verdict tone="good" title="Correct." /> : null}
              {attempt.outcome === "recovered" ? (
                <Verdict tone="good" title="Correct, on the second try." />
              ) : null}
              {attempt.outcome === "open" && misconception ? (
                <Verdict
                  tone="bad"
                  title="Not quite."
                  hint={misconception.hint}
                  note="You can try once more."
                />
              ) : null}
              {attempt.outcome === "missed" && misconception ? (
                <Verdict
                  tone="bad"
                  title="Not this time."
                  hint={misconception.hint}
                  note={
                    question.kind === "choice"
                      ? "The correct answer is marked."
                      : "The right order is shown."
                  }
                />
              ) : null}
            </div>

            {lastAnswer && pinned ? (
              <div className="flex flex-col gap-2 sm:flex-row">
                <SimulatorSheet
                  code={lastAnswer.code}
                  pinned={pinned}
                  open={sheetOpen}
                  onOpenChange={openSheet}
                  onExplain={misconception ? explain : undefined}
                  onCloseAutoFocus={(event) => {
                    if (!focusWorked.current) return;
                    focusWorked.current = false;
                    event.preventDefault();
                    workedHeadingRef.current?.focus();
                  }}
                  trigger={
                    <Button
                      type="button"
                      variant={attempt.outcome === "missed" ? "default" : "outline"}
                    >
                      Show me what happens
                    </Button>
                  }
                />
                {misconception && attempt.sheetSeen && !attempt.workedOpen ? (
                  <Button type="button" variant="outline" onClick={showWorked}>
                    Explain it like a worked example
                  </Button>
                ) : null}
                {finished && !attempt.workedOpen ? (
                  <Button
                    type="button"
                    variant={attempt.outcome === "missed" ? "outline" : "default"}
                    onClick={next}
                    className="sm:ml-auto"
                  >
                    {upcoming ? "Next question" : "See summary"}
                    <ArrowRight aria-hidden="true" />
                  </Button>
                ) : null}
              </div>
            ) : null}

            {attempt.workedOpen && misconception ? (
              <WorkedExample
                key={`${question.id}:${misconception.id}`}
                misconception={misconception}
                headingRef={workedHeadingRef}
                onTryAnother={next}
                isLast={!upcoming}
              />
            ) : null}
          </section>
        )}
      </main>
    </div>
  );
}

function countOutcome(stats: Stats, outcome: Outcome): number {
  return Object.values(stats).reduce(
    (n, t) => n + t.results.filter((r) => r === outcome).length,
    0,
  );
}

function Verdict({
  tone,
  title,
  hint,
  note,
}: {
  tone: "good" | "bad";
  title: string;
  hint?: string;
  note?: ReactNode;
}) {
  return (
    <div className="space-y-1 border-border border-t pt-4">
      <p
        className={
          tone === "good"
            ? "font-heading font-semibold text-lg text-primary tracking-tight"
            : "font-heading font-semibold text-destructive text-lg tracking-tight"
        }
      >
        {title}
      </p>
      {hint ? (
        <p className="max-w-prose text-foreground text-sm leading-6">
          <Inline text={hint} />
        </p>
      ) : null}
      {note ? <p className="text-muted-foreground text-sm">{note}</p> : null}
    </div>
  );
}
