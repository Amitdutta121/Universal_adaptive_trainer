"use client";

/**
 * Student-experience design prototype — the whole learner-facing flow on mock
 * data, with no API and no LLM calls. See `mock-data.ts` for the stand-in
 * selection / scoring / mastery logic and `session-types.ts` for the state shape.
 *
 * Kept deliberately separate from the console: its own route under
 * `/experiments`, its own full-page shell (AppChrome skips it), its own state.
 * Nothing here imports the API client.
 */

import { FlaskConical, Home } from "lucide-react";
import { useCallback, useEffect, useReducer, useRef, useState } from "react";
import { toast } from "sonner";
import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogClose,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Skeleton } from "@/components/ui/skeleton";
import { ProgressAside } from "./components/progress-aside";
import { QuestionPanel } from "./components/question-panel";
import { ResultPanel } from "./components/result-panel";
import { SummaryPanel } from "./components/summary-panel";
import { WelcomePanel } from "./components/welcome-panel";
import {
  applyOutcome,
  initialProgress,
  practiceSetById,
  questionById,
  scoreAnswer,
  scoreLabelText,
  selectNextQuestion,
  shuffledStepIds,
} from "./mock-data";
import {
  EMPTY_SESSION,
  NAME_STORAGE_KEY,
  SESSION_STORAGE_KEY,
  type SessionState,
} from "./session-types";

// ---------------------------------------------------------------------------
// Reducer
// ---------------------------------------------------------------------------

type Action =
  | { type: "RESTORE"; state: SessionState }
  | { type: "START"; setId: string; name: string }
  | { type: "QUESTION_READY"; selection: NonNullable<SessionState["current"]> }
  | { type: "QUESTION_EMPTY" }
  | {
      type: "SUBMIT_SUCCESS";
      result: NonNullable<SessionState["lastResult"]>;
      attempt: SessionState["attempts"][number];
      nextProgress: NonNullable<SessionState["progress"]>;
    }
  | { type: "NEXT" }
  | { type: "END_SESSION" }
  | { type: "RESET" };

function reducer(state: SessionState, action: Action): SessionState {
  switch (action.type) {
    case "RESTORE":
      return action.state;

    case "START": {
      const set = practiceSetById(action.setId);
      if (!set) return state;
      return {
        ...EMPTY_SESSION,
        phase: "loading",
        setId: set.id,
        learnerName: action.name,
        seed: (Date.now() % 100000) + 1,
        step: 1,
        progress: initialProgress(set),
        announcement: "Loading your first question.",
      };
    }

    case "QUESTION_READY":
      return {
        ...state,
        phase: "question",
        current: action.selection,
        announcement: `Question ${action.selection.ordinal}, ${action.selection.servedDifficulty} difficulty, ${action.selection.question.subtopicName}.`,
      };

    case "QUESTION_EMPTY":
      return {
        ...state,
        phase: "summary",
        current: null,
        announcement: "You've answered every question in this set.",
      };

    case "SUBMIT_SUCCESS":
      return {
        ...state,
        phase: "result",
        progress: action.nextProgress,
        answeredIds: [...state.answeredIds, action.result.questionId],
        attempts: [...state.attempts, action.attempt],
        lastResult: action.result,
        announcement: `Answer scored ${action.result.score} out of 100 — ${scoreLabelText(
          action.result.label,
        )}. ${action.result.topicName} mastery is now ${Math.round(
          action.result.topicAfter * 100,
        )} percent.`,
      };

    case "NEXT":
      return {
        ...state,
        phase: "loading",
        current: null,
        lastResult: null,
        step: state.step + 1,
        announcement: "Loading the next question.",
      };

    case "END_SESSION":
      return {
        ...state,
        phase: "summary",
        current: null,
        announcement: "Session ended. Here is your summary.",
      };

    case "RESET":
      return { ...EMPTY_SESSION };

    default:
      return state;
  }
}

// ---------------------------------------------------------------------------
// Small hooks
// ---------------------------------------------------------------------------

function useReducedMotion(): boolean {
  const [reduced, setReduced] = useState(false);
  useEffect(() => {
    const query = window.matchMedia("(prefers-reduced-motion: reduce)");
    setReduced(query.matches);
    const handler = (event: MediaQueryListEvent) => setReduced(event.matches);
    query.addEventListener("change", handler);
    return () => query.removeEventListener("change", handler);
  }, []);
  return reduced;
}

function readSavedSession(): SessionState | null {
  try {
    const raw = window.localStorage.getItem(SESSION_STORAGE_KEY);
    if (!raw) return null;
    const parsed = JSON.parse(raw) as SessionState;
    if (!parsed || typeof parsed !== "object") return null;
    if (!parsed.setId || !practiceSetById(parsed.setId)) return null;
    return parsed;
  } catch {
    return null;
  }
}

// ---------------------------------------------------------------------------
// Screen
// ---------------------------------------------------------------------------

const LOADING_MESSAGE_DELAY_MS = 550;

export function StudentExperience() {
  const [state, dispatch] = useReducer(reducer, EMPTY_SESSION);
  const reduceMotion = useReducedMotion();

  const [answer, setAnswer] = useState("");
  const [parsonsOrder, setParsonsOrder] = useState<string[]>([]);
  const [submitting, setSubmitting] = useState(false);
  const [submitError, setSubmitError] = useState<string | null>(null);
  const [forceFail, setForceFail] = useState(false);
  const [resetOpen, setResetOpen] = useState(false);
  const [endOpen, setEndOpen] = useState(false);

  const [savedSnapshot, setSavedSnapshot] = useState<SessionState | null>(null);
  const [defaultName, setDefaultName] = useState("");
  const [defaultSetId, setDefaultSetId] = useState("foundations");

  const hydratedRef = useRef(false);
  const prevPhaseRef = useRef(state.phase);
  const questionFocusRef = useRef<HTMLDivElement>(null);
  const resultFocusRef = useRef<HTMLDivElement>(null);

  const set = state.setId ? practiceSetById(state.setId) : undefined;
  const remaining = set ? set.questionIds.length - state.answeredIds.length : 0;
  const averageScore =
    state.attempts.length === 0
      ? null
      : Math.round(
          state.attempts.reduce((sum, attempt) => sum + attempt.score, 0) / state.attempts.length,
        );
  const streak = (() => {
    let count = 0;
    for (let i = state.attempts.length - 1; i >= 0; i -= 1) {
      if (state.attempts[i].score >= 80) count += 1;
      else break;
    }
    return count;
  })();

  // Restore once, on mount. Never auto-navigates into a run — the welcome screen
  // offers "Resume" instead, so the entry page is always what a learner sees first.
  useEffect(() => {
    const url = new URLSearchParams(window.location.search);
    const urlSet = url.get("set");
    if (urlSet && practiceSetById(urlSet)) setDefaultSetId(urlSet);

    try {
      const rememberedName = window.localStorage.getItem(NAME_STORAGE_KEY);
      if (rememberedName) setDefaultName(rememberedName);
    } catch {
      // localStorage unavailable — fall back to an empty name.
    }

    const saved = readSavedSession();
    if (saved && saved.phase !== "welcome" && saved.answeredIds.length > 0) {
      setSavedSnapshot(saved);
      if (!urlSet && saved.setId) setDefaultSetId(saved.setId);
    }
    hydratedRef.current = true;
  }, []);

  // Persist the live session, and keep the active set in the URL so a shared or
  // reloaded link defaults to the same practice set. The phase is deliberately
  // not in the URL — it can't be reconstructed on a cold load, so `localStorage`
  // + the welcome screen's "Resume" is the single recovery path.
  useEffect(() => {
    if (!hydratedRef.current) return;
    try {
      window.localStorage.setItem(SESSION_STORAGE_KEY, JSON.stringify(state));
      if (state.learnerName) {
        window.localStorage.setItem(NAME_STORAGE_KEY, state.learnerName);
      }
    } catch {
      // Persistence is a convenience; ignore quota / privacy-mode failures.
    }
    window.history.replaceState(
      null,
      "",
      state.setId
        ? `${window.location.pathname}?set=${encodeURIComponent(state.setId)}`
        : window.location.pathname,
    );
  }, [state]);

  // Serve the next question after a short, honest "thinking" beat. Keyed on the
  // step counter so it fires once per served question; the set/progress/answered
  // inputs are read fresh when the timer resolves and are fixed for a given step.
  // biome-ignore lint/correctness/useExhaustiveDependencies: intentionally step-gated
  useEffect(() => {
    if (state.phase !== "loading" || !set || !state.progress) return;
    const progress = state.progress;
    const timer = window.setTimeout(
      () => {
        const selection = selectNextQuestion({
          set,
          progress,
          answeredIds: state.answeredIds,
          seed: state.seed,
        });
        if (selection) dispatch({ type: "QUESTION_READY", selection });
        else dispatch({ type: "QUESTION_EMPTY" });
      },
      reduceMotion ? 150 : LOADING_MESSAGE_DELAY_MS,
    );
    return () => window.clearTimeout(timer);
  }, [state.phase, state.step]);

  // Reset the answer widgets whenever a new question is shown.
  useEffect(() => {
    if (state.phase === "question" && state.current) {
      setAnswer("");
      setSubmitError(null);
      setParsonsOrder(
        state.current.question.type === "parsons" ? shuffledStepIds(state.current.question) : [],
      );
    }
  }, [state.phase, state.current]);

  // Move focus to the panel that just appeared, but only on a real transition
  // (not on first paint or a persist-driven re-render).
  useEffect(() => {
    if (!hydratedRef.current) return;
    if (prevPhaseRef.current === state.phase) return;
    prevPhaseRef.current = state.phase;
    if (state.phase === "question") questionFocusRef.current?.focus();
    if (state.phase === "result") resultFocusRef.current?.focus();
  }, [state.phase]);

  const runScore = useCallback(() => {
    if (!state.current || !state.progress) return;
    const question = state.current.question;
    const ordinal = state.current.ordinal;
    const progress = state.progress;
    const raw = question.type === "parsons" ? JSON.stringify(parsonsOrder) : answer;
    setSubmitting(true);
    // A tiny delay so the button's "Scoring…" state is perceptible.
    window.setTimeout(() => {
      const result = scoreAnswer(question, raw);
      const shift = applyOutcome(progress, question, result.score);
      setSubmitting(false);
      setSubmitError(null);
      dispatch({
        type: "SUBMIT_SUCCESS",
        nextProgress: shift.next,
        result: {
          ...result,
          questionId: question.id,
          answer: raw,
          topicName: shift.topicName,
          topicBefore: shift.topicBefore,
          topicAfter: shift.topicAfter,
        },
        attempt: {
          ordinal,
          questionId: question.id,
          questionPrompt: question.prompt,
          topicName: question.topicName,
          subtopicName: question.subtopicName,
          answer: raw,
          score: result.score,
          label: result.label,
        },
      });
    }, 260);
  }, [answer, parsonsOrder, state.current, state.progress]);

  const handleSubmit = useCallback(() => {
    if (forceFail) {
      setForceFail(false);
      setSubmitError("The connection dropped before the answer reached the server (simulated).");
      return;
    }
    runScore();
  }, [forceFail, runScore]);

  const handleRetry = useCallback(() => {
    setSubmitError(null);
    runScore();
  }, [runScore]);

  const handleNext = useCallback(() => {
    if (remaining <= 0) {
      dispatch({ type: "END_SESSION" });
      return;
    }
    dispatch({ type: "NEXT" });
  }, [remaining]);

  const handleStart = useCallback((setId: string, name: string) => {
    setSavedSnapshot(null);
    dispatch({ type: "START", setId, name });
  }, []);

  const handleResume = useCallback(() => {
    if (savedSnapshot) {
      prevPhaseRef.current = "welcome";
      dispatch({ type: "RESTORE", state: savedSnapshot });
      setSavedSnapshot(null);
    }
  }, [savedSnapshot]);

  const handleReset = useCallback(() => {
    try {
      window.localStorage.removeItem(SESSION_STORAGE_KEY);
    } catch {
      // ignore
    }
    setSavedSnapshot(null);
    setAnswer("");
    setParsonsOrder([]);
    setSubmitError(null);
    setForceFail(false);
    setResetOpen(false);
    setEndOpen(false);
    prevPhaseRef.current = "welcome";
    dispatch({ type: "RESET" });
    toast.success("Prototype reset", { description: "The practice session was cleared." });
  }, []);

  const savedSummary = savedSnapshot?.setId
    ? `${savedSnapshot.answeredIds.length} answered · ${
        practiceSetById(savedSnapshot.setId)?.label ?? "practice set"
      }`
    : null;

  return (
    <div className="min-h-screen bg-background text-foreground">
      <a
        href="#practice-main"
        className="sr-only rounded-md bg-primary px-3 py-2 font-medium text-primary-foreground text-sm focus:not-sr-only focus:absolute focus:top-3 focus:left-3 focus:z-50"
      >
        Skip to content
      </a>

      <div className="sr-only" role="status" aria-live="polite">
        {state.announcement}
      </div>

      <header className="border-border border-b bg-card/60">
        <div className="mx-auto flex max-w-5xl flex-wrap items-center justify-between gap-3 px-4 py-3 sm:px-6">
          <div className="flex items-center gap-2.5">
            <span className="flex size-8 items-center justify-center rounded-lg bg-primary text-primary-foreground">
              <FlaskConical className="size-4" aria-hidden="true" />
            </span>
            <span>
              <span className="block font-mono text-[0.68rem] text-muted-foreground uppercase tracking-widest">
                Design prototype
              </span>
              <span className="block font-heading font-semibold text-foreground text-sm">
                Student experience
              </span>
            </span>
          </div>
          <div className="flex items-center gap-2">
            {state.phase === "question" || state.phase === "result" ? (
              <Button type="button" variant="ghost" size="sm" onClick={() => setEndOpen(true)}>
                End session
              </Button>
            ) : null}
            <a
              href="/"
              className="inline-flex items-center gap-1.5 rounded-md border border-border px-2.5 py-1.5 text-muted-foreground text-sm hover:text-foreground"
            >
              <Home className="size-3.5" aria-hidden="true" />
              Console
            </a>
          </div>
        </div>
      </header>

      <div className="mx-auto max-w-5xl px-4 py-3 sm:px-6">
        <p className="rounded-lg border border-amber-500/30 bg-amber-500/10 px-3 py-2 text-amber-800 text-sm dark:text-amber-200">
          <strong className="font-medium">Prototype.</strong> Every question, score and mastery
          number here is mock data generated in the browser — there are no server or model calls. It
          exists to review the student-facing design.
        </p>
      </div>

      <main id="practice-main" className="mx-auto max-w-5xl px-4 pb-16 sm:px-6" tabIndex={-1}>
        {state.phase === "welcome" ? (
          <WelcomePanel
            defaultName={defaultName}
            defaultSetId={defaultSetId}
            hasSavedSession={savedSnapshot !== null}
            savedSummary={savedSummary}
            onResume={handleResume}
            onStart={handleStart}
          />
        ) : null}

        {state.phase !== "welcome" && state.phase !== "summary" && set && state.progress ? (
          <div className="grid gap-6 lg:grid-cols-[minmax(0,1fr)_18rem] lg:items-start">
            <div className="min-w-0 space-y-6">
              <div className="flex flex-wrap items-center justify-between gap-2 text-sm">
                <span className="font-medium text-foreground">{set.label}</span>
                <span className="text-muted-foreground tabular-nums">
                  {state.answeredIds.length} answered · {Math.max(remaining, 0)} left
                </span>
              </div>

              {state.phase === "loading" ? (
                <div
                  className="space-y-4 rounded-xl border border-border bg-card p-5 ring-1 ring-foreground/5 sm:p-6"
                  aria-hidden="true"
                >
                  <Skeleton className="h-6 w-40" />
                  <Skeleton className="h-24 w-full" />
                  <Skeleton className="h-10 w-full" />
                  <Skeleton className="h-10 w-full" />
                  <Skeleton className="h-11 w-40" />
                </div>
              ) : null}

              {state.phase === "question" && state.current ? (
                <div
                  ref={questionFocusRef}
                  tabIndex={-1}
                  className="rounded-xl outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2 focus-visible:ring-offset-background"
                >
                  <QuestionPanel
                    selection={state.current}
                    answer={answer}
                    onAnswerChange={setAnswer}
                    parsonsOrder={parsonsOrder}
                    onParsonsReorder={setParsonsOrder}
                    onSubmit={handleSubmit}
                    submitting={submitting}
                    submitError={submitError}
                    onRetry={handleRetry}
                    streak={streak}
                  />
                </div>
              ) : null}

              {state.phase === "result" && state.lastResult ? (
                <ResultPanel
                  ref={resultFocusRef}
                  result={state.lastResult}
                  question={
                    questionById(state.lastResult.questionId) ??
                    (state.current?.question as NonNullable<typeof state.current>["question"])
                  }
                  onNext={handleNext}
                  reduceMotion={reduceMotion}
                  isLastInSet={remaining <= 0}
                />
              ) : null}
            </div>

            <ProgressAside
              progress={state.progress}
              answered={state.answeredIds.length}
              averageScore={averageScore}
              reduceMotion={reduceMotion}
            />
          </div>
        ) : null}

        {state.phase === "summary" && state.progress ? (
          <SummaryPanel
            learnerName={state.learnerName}
            setLabel={set?.label ?? "this set"}
            attempts={state.attempts}
            progress={state.progress}
            averageScore={averageScore}
            everythingAnswered={remaining <= 0 && state.attempts.length > 0}
            reduceMotion={reduceMotion}
            onPracticeAgain={() => {
              prevPhaseRef.current = "summary";
              dispatch({ type: "RESET" });
            }}
            onStartOver={() => setResetOpen(true)}
          />
        ) : null}

        <div className="mt-10 rounded-lg border border-border border-dashed p-3">
          <div className="flex flex-wrap items-center justify-between gap-2">
            <span className="font-mono text-muted-foreground text-xs uppercase tracking-widest">
              Prototype controls
            </span>
            <Button type="button" variant="ghost" size="sm" onClick={() => setResetOpen(true)}>
              Reset prototype
            </Button>
          </div>
          <label className="mt-2 flex items-center gap-2 text-muted-foreground text-sm">
            <input
              type="checkbox"
              checked={forceFail}
              onChange={(event) => setForceFail(event.target.checked)}
              className="size-4 accent-[var(--primary)]"
            />
            Make the next answer submit fail once, to preview the recovery flow.
          </label>
        </div>
      </main>

      <Dialog open={resetOpen} onOpenChange={setResetOpen}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>Reset this prototype?</DialogTitle>
            <DialogDescription>
              This clears the {state.attempts.length} answered{" "}
              {state.attempts.length === 1 ? "question" : "questions"} and all mastery from this
              practice session on this device. It can't be undone.
            </DialogDescription>
          </DialogHeader>
          <DialogFooter>
            <DialogClose asChild>
              <Button type="button" variant="outline">
                Keep practising
              </Button>
            </DialogClose>
            <Button type="button" variant="destructive" onClick={handleReset}>
              Reset prototype
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      <Dialog open={endOpen} onOpenChange={setEndOpen}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>End this session?</DialogTitle>
            <DialogDescription>
              You've answered {state.attempts.length}{" "}
              {state.attempts.length === 1 ? "question" : "questions"}. You'll go to the summary;
              your progress stays saved and you can practise another set from there.
            </DialogDescription>
          </DialogHeader>
          <DialogFooter>
            <DialogClose asChild>
              <Button type="button" variant="outline">
                Keep going
              </Button>
            </DialogClose>
            <Button
              type="button"
              onClick={() => {
                setEndOpen(false);
                prevPhaseRef.current = state.phase;
                dispatch({ type: "END_SESSION" });
              }}
            >
              End session
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  );
}
