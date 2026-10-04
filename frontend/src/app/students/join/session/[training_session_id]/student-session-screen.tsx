"use client";

import {
  AlertCircle,
  ArrowLeft,
  ArrowRight,
  ArrowUpRight,
  CheckCircle2,
  CircleDashed,
  Flame,
  Lightbulb,
  Loader2,
  Sparkles,
  XCircle,
} from "lucide-react";
import type { Route } from "next";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { useMemo, useState } from "react";
import { CollapsiblePanel } from "@/components/collapsible-panel";
import { QueryError, TableSkeleton } from "@/components/query-state";
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Progress } from "@/components/ui/progress";
import {
  Sheet,
  SheetContent,
  SheetDescription,
  SheetHeader,
  SheetTitle,
} from "@/components/ui/sheet";
import { ApiError } from "@/lib/api/client";
import {
  useAnswerAttempt,
  useAttemptReview,
  useEndTrainingSession,
  useNextQuestion,
  useRequestLiveQuestion,
  useTrainingSession,
  useTrainingSessionProgress,
} from "@/lib/api/queries";
import type {
  AnsweredOut,
  AttemptOut,
  QuestionDetail,
  ServedQuestionOut,
  StudentProgressOut,
} from "@/lib/api/types";
import {
  questionTypeUI,
  questionTypeLabel as registryTypeLabel,
} from "@/lib/question-types/registry";
import { CodeAnswerInput } from "@/lib/question-types/text-answer";
import { cn } from "@/lib/utils";

// Color/urgency bucket for a 0-100 score: full credit, partial credit, or none.
function scoreTone(score: number) {
  if (score >= 100) return "success";
  if (score > 0) return "warn";
  return "error";
}

// Human label for the same 0-100 score the tone above colors.
function formatResultLabel(score: number) {
  if (score >= 100) return "Correct";
  if (score > 0) return "Partly correct";
  return "Incorrect";
}

// Icon paired with the tone/label above for the result banner.
function resultIcon(score: number) {
  if (score >= 100) return CheckCircle2;
  if (score > 0) return CircleDashed;
  return XCircle;
}

// Localized, human-readable timestamp for session/attempt display.
function learnerDate(value: string) {
  return new Intl.DateTimeFormat(undefined, {
    dateStyle: "medium",
    timeStyle: "short",
  }).format(new Date(value));
}

// The registry's display name ("Numeric response"), the same label the Studio shows.
function questionTypeLabel(questionType: ServedQuestionOut["question_type"]) {
  return questionType ? registryTypeLabel(questionType) : "";
}

// Same tone bucketing as `scoreTone`, but for a past attempt that may still
// be open (unscored), which `scoreTone` has no case for.
function attemptTone(attempt: AttemptOut) {
  if (attempt.score === null) return "current";
  if (attempt.score >= 100) return "success";
  if (attempt.score > 0) return "warn";
  return "error";
}

// BKT's p_known is a 0-1 probability; clamp defensively before feeding a
// Progress bar, which expects 0-100.
function masteryPercent(value: number) {
  return Math.max(0, Math.min(100, value * 100));
}

// Weakness is likewise stored as 0-1 (see INITIAL_SUBTOPIC_WEAKNESS in
// app/domain/mastery.py), so the same clamp-and-scale applies.
function weaknessPercent(value: number) {
  return Math.max(0, Math.min(100, value * 100));
}

/**
 * The stored ``content`` dict carries the answer key -- ``correct_option_index``,
 * ``correct_answer``, ``expected_output``, ``correct_order`` -- which is why the
 * student-facing serve schema never publishes it (see `ServedQuestionOut`). Once a
 * question is answered there is nothing left to protect, so this same field is
 * read back here to show the student what was actually correct.
 */
function answerKeyContent(detail: QuestionDetail): Record<string, unknown> {
  return (detail.content ?? {}) as Record<string, unknown>;
}

// The author's explanation for a discrete question -- the same string the
// scorer hands back as `detail` at answer time (see `_explanation` in
// app/adaptive/scoring.py). Executable types have no stored explanation;
// their feedback was live test evidence and is not retained per attempt.
function explanationText(content: Record<string, unknown>): string | null {
  const text = content.explanation;
  return typeof text === "string" && text.trim() !== "" ? text : null;
}

// Reference solution + test source for the executable question types
// (coding/debugging/code_completion), the one place this pair carries
// information the type-specific reviews above don't already show.
function ReferenceSolutionBlock({ detail }: { detail: QuestionDetail }) {
  return (
    <>
      {detail.reference_solution ? (
        <div className="space-y-2">
          <div className="font-medium text-foreground text-sm">Reference solution</div>
          <pre className="overflow-x-auto rounded-[1rem] border border-border/70 bg-slate-950 p-4 font-mono text-[13px] text-slate-50 leading-6">
            {detail.reference_solution}
          </pre>
        </div>
      ) : null}

      {detail.tests ? (
        <div className="space-y-2">
          <div className="font-medium text-foreground text-sm">Tests</div>
          <pre className="overflow-x-auto rounded-[1rem] border border-border/70 bg-muted/20 p-4 font-mono text-[13px] text-foreground leading-6">
            {detail.tests}
          </pre>
        </div>
      ) : null}
    </>
  );
}

/**
 * What was actually correct, read back from an answered question. Shared by the
 * in-flow result card (which also knows what the student submitted) and the past
 * question sheet (which only knows the question, not the historical submission).
 */
function AnswerReview({
  detail,
  submittedAnswer,
}: {
  detail: QuestionDetail;
  submittedAnswer?: string;
}) {
  const content = answerKeyContent(detail);
  const questionType = detail.question.question_type;
  const typeUI = questionTypeUI(questionType);
  // For MCQ / true-false / output-prediction / parsons the stored "reference
  // solution" is just the correct option/answer/order restated -- already shown
  // above by the type-specific review, so showing it again would be redundant.
  // It carries new information only for the executable formats.
  const showReferenceSolution = questionType === null || (typeUI?.showReferenceSolution ?? false);

  return (
    <div className="space-y-4">
      {typeUI ? <typeUI.ReviewContent content={content} submittedAnswer={submittedAnswer} /> : null}
      {showReferenceSolution ? <ReferenceSolutionBlock detail={detail} /> : null}
    </div>
  );
}

// Side panel for revisiting a question from earlier in the session. An
// unanswered attempt still hides its solution (it may be the current
// question, resumed); an answered one gets the same answer-key review as
// the in-flow result card.
function PastQuestionSheet({
  attempt,
  detail,
  isOpen,
  onOpenChange,
  onPrev,
  onNext,
  hasPrev,
  hasNext,
}: {
  attempt: AttemptOut | null;
  detail: QuestionDetail | null;
  isOpen: boolean;
  onOpenChange: (open: boolean) => void;
  onPrev: () => void;
  onNext: () => void;
  hasPrev: boolean;
  hasNext: boolean;
}) {
  const isAnsweredAttempt = attempt?.score !== null;
  const feedbackText = detail ? explanationText(answerKeyContent(detail)) : null;

  return (
    <Sheet open={isOpen} onOpenChange={onOpenChange}>
      <SheetContent
        side="right"
        className="w-full max-w-2xl overflow-y-auto border-border border-l bg-background p-0 sm:max-w-2xl"
      >
        <SheetHeader className="border-border/70 border-b px-5 py-4">
          <SheetTitle>{attempt ? `Question ${attempt.ordinal}` : "Past question"}</SheetTitle>
          <SheetDescription>
            Review a past question, then close this panel to continue the current session.
          </SheetDescription>
          {/* Step through this run's earlier questions without closing the panel;
              order matches the "Recent questions" list (oldest to newest). */}
          <div className="flex items-center gap-2 pt-1">
            <Button type="button" variant="outline" size="sm" onClick={onPrev} disabled={!hasPrev}>
              <ArrowLeft />
              Previous
            </Button>
            <Button type="button" variant="outline" size="sm" onClick={onNext} disabled={!hasNext}>
              Next
              <ArrowRight />
            </Button>
          </div>
        </SheetHeader>

        <div className="space-y-5 px-5 py-5">
          {attempt ? (
            <div className="flex flex-wrap items-center gap-2">
              <Badge variant="outline">Attempt #{attempt.id}</Badge>
              <Badge variant="outline">{attempt.served_difficulty}</Badge>
              {attempt.question_type ? (
                <Badge variant="outline">{questionTypeLabel(attempt.question_type)}</Badge>
              ) : null}
              <Badge
                variant={
                  attempt.score === null
                    ? "outline"
                    : attempt.score >= 100
                      ? "secondary"
                      : attempt.score > 0
                        ? "outline"
                        : "destructive"
                }
              >
                {attempt.score === null ? "Open" : `${attempt.score.toFixed(0)} / 100`}
              </Badge>
            </div>
          ) : null}

          {detail ? (
            <>
              <div className="space-y-2">
                <div className="font-medium text-foreground text-sm">
                  {detail.taxonomy.topic}
                  {detail.taxonomy.subtopics.length > 0
                    ? ` - ${detail.taxonomy.subtopics.join(", ")}`
                    : ""}
                </div>
                <div className="whitespace-pre-wrap rounded-[1rem] border border-border/70 bg-card/80 px-4 py-4 text-foreground text-sm leading-7">
                  {detail.question.prompt}
                </div>
              </div>

              {!isAnsweredAttempt ? (
                <div className="rounded-[1rem] border border-amber-500/25 bg-amber-50 px-4 py-3 text-amber-900 text-sm">
                  This question is still active in the session, so its solution details are hidden.
                </div>
              ) : (
                <>
                  {feedbackText ? (
                    <div className="space-y-1.5">
                      <div className="font-medium text-foreground text-sm">Feedback</div>
                      <pre className="overflow-x-auto whitespace-pre-wrap text-foreground text-sm leading-7">
                        {feedbackText}
                      </pre>
                    </div>
                  ) : null}
                  {/* Same review as the in-flow result card, and passing the
                      stored submission marks the learner's own choice beside
                      the correct one. */}
                  <AnswerReview detail={detail} submittedAnswer={attempt?.answer ?? undefined} />
                </>
              )}
            </>
          ) : (
            <div className="text-muted-foreground text-sm">Loading question details…</div>
          )}
        </div>
      </SheetContent>
    </Sheet>
  );
}

// The input widget for the current question, shaped by its question_type:
// radio options for MCQ/true-false, the drag-and-drop composer for Parsons,
// or a free-text box (with a Ctrl/Cmd+Enter shortcut) for everything else.
function AnswerForm({
  question,
  answer,
  onAnswerChange,
  onSubmit,
  submitting,
}: {
  question: ServedQuestionOut;
  answer: string;
  onAnswerChange: (value: string) => void;
  onSubmit: () => void;
  submitting: boolean;
}) {
  const canSubmit = !submitting && answer.trim().length > 0;
  // A type with no built UI (or no type at all) gets the free-text code box.
  const AnswerInput = questionTypeUI(question.question_type)?.AnswerInput ?? CodeAnswerInput;

  return (
    <div className="space-y-5">
      <AnswerInput
        question={question}
        value={answer}
        onChange={onAnswerChange}
        onSubmit={onSubmit}
      />

      <div className="flex flex-col gap-3 rounded-[1.35rem] border border-border/70 bg-white/70 p-4 shadow-[0_18px_38px_-30px_rgb(19_26_28_/_0.26)] backdrop-blur-sm sm:flex-row sm:items-center sm:justify-between">
        <div className="space-y-1">
          <div className="font-medium text-foreground text-sm">Ready to submit?</div>
          <p className="text-muted-foreground text-sm">
            Give it one last look — once submitted, this answer is scored and locked in.
          </p>
        </div>
        <Button
          type="button"
          size="lg"
          disabled={!canSubmit}
          onClick={onSubmit}
          className="min-w-44 rounded-full px-5 shadow-[0_20px_40px_-28px_rgb(20_91_84_/_0.6)]"
        >
          <ArrowRight />
          Submit answer
        </Button>
      </div>
    </div>
  );
}

// The post-submit screen: score, the backend's own feedback text (an
// authored explanation for discrete types, or live test-failure evidence
// for executable ones -- see `score_answer` in app/adaptive/scoring.py),
// the mastery shift, and the answer-key review once it has loaded.
function ResultCard({
  result,
  detail,
  submittedAnswer,
  onNext,
}: {
  result: AnsweredOut;
  detail: QuestionDetail | null;
  submittedAnswer: string;
  onNext: () => void;
}) {
  const tone = scoreTone(result.score);
  const Icon = resultIcon(result.score);
  const badgeVariant =
    tone === "success" ? "secondary" : tone === "warn" ? "outline" : "destructive";
  const toneClasses =
    tone === "success"
      ? "border-emerald-500/25"
      : tone === "warn"
        ? "border-amber-500/25"
        : "border-rose-500/25";

  return (
    <Card
      className={`rounded-[1.5rem] border bg-white/92 shadow-[0_18px_40px_-34px_rgb(19_26_28_/_0.24)] ${toneClasses}`}
    >
      <CardHeader className="gap-4 px-5 py-5 sm:px-6">
        <div className="flex flex-col gap-4 sm:flex-row sm:items-start sm:justify-between">
          <div className="space-y-3">
            <div className="flex flex-wrap items-center gap-3">
              <div className="flex items-center gap-3">
                <div className="rounded-full border border-border/70 p-2">
                  <Icon className="size-4" />
                </div>
                <CardTitle className="text-xl">Result</CardTitle>
              </div>
              <Badge variant={badgeVariant} className="rounded-full px-2.5">
                {formatResultLabel(result.score)}
              </Badge>
            </div>
            <div className="flex flex-wrap items-end gap-x-4 gap-y-2">
              <div className="font-heading font-semibold text-4xl text-foreground tracking-[-0.03em]">
                {result.score.toFixed(0)}
                <span className="ml-2 font-medium font-sans text-base text-muted-foreground">
                  / 100
                </span>
              </div>
              {result.total_tests ? (
                <div className="pb-1 text-muted-foreground text-sm">
                  {result.passed_tests} of {result.total_tests} tests passed
                </div>
              ) : null}
            </div>
          </div>
          <Button type="button" onClick={onNext} className="rounded-full px-4 sm:self-end">
            <ArrowRight />
            Next question
          </Button>
        </div>
      </CardHeader>
      <CardContent className="space-y-5 px-5 pb-5 sm:px-6">
        {result.detail ? (
          <div className="space-y-1.5">
            <div className="font-medium text-foreground text-sm">Feedback</div>
            <pre className="overflow-x-auto whitespace-pre-wrap text-foreground text-sm leading-7">
              {result.detail}
            </pre>
          </div>
        ) : null}

        {result.mastery_before !== null && result.mastery_after !== null ? (
          <div className="space-y-2.5">
            <div className="flex items-center justify-between gap-3">
              <span className="font-medium text-foreground text-sm">Topic mastery</span>
              <span className="text-muted-foreground text-sm">
                {result.mastery_before.toFixed(3)} to{" "}
                <strong className="text-foreground">{result.mastery_after.toFixed(3)}</strong>
              </span>
            </div>
            <Progress
              value={Math.max(0, Math.min(100, result.mastery_after * 100))}
              className="h-2"
            />
          </div>
        ) : null}

        <div className="space-y-3 border-border/60 border-t pt-4">
          <div className="flex items-center gap-2 font-medium text-foreground text-sm">
            <Lightbulb className="size-4 text-primary" />
            What was correct
          </div>
          {detail ? (
            <AnswerReview detail={detail} submittedAnswer={submittedAnswer} />
          ) : (
            <p className="text-muted-foreground text-sm">Loading the correct answer…</p>
          )}
        </div>
      </CardContent>
    </Card>
  );
}

// This run's served questions, most recent first, as a toggleable list in
// the sidebar rather than a row of pills in the header -- open by default
// since jumping back to a question is a common thing to want, but
// collapsible because the list grows across a long session.
function RecentQuestionsPanel({
  attempts,
  onSelect,
}: {
  attempts: AttemptOut[];
  onSelect: (attempt: AttemptOut) => void;
}) {
  const ordered = [...attempts].reverse();

  return (
    <CollapsiblePanel
      title="Recent questions"
      summary={`${attempts.length} from this run`}
      openLabel="Show"
      closeLabel="Hide"
      defaultOpen
    >
      {ordered.length === 0 ? (
        <p className="text-muted-foreground text-xs">Nothing served yet this run.</p>
      ) : (
        <div className="space-y-1.5">
          {ordered.map((attempt) => (
            <button
              key={attempt.id}
              type="button"
              onClick={() => onSelect(attempt)}
              className={cn(
                "flex w-full items-center justify-between gap-3 rounded-lg border px-2.5 py-2 text-left text-xs transition-colors hover:bg-white",
                attemptTone(attempt) === "success" && "border-emerald-500/25 bg-emerald-50/70",
                attemptTone(attempt) === "warn" && "border-amber-500/25 bg-amber-50/70",
                attemptTone(attempt) === "error" && "border-rose-500/25 bg-rose-50/70",
                attemptTone(attempt) === "current" && "border-border/60 bg-background",
              )}
            >
              <span className="min-w-0 truncate">
                <span className="font-medium text-foreground">Q{attempt.ordinal}</span>
                {attempt.question_type ? (
                  <span className="ml-1.5 text-muted-foreground">
                    {questionTypeLabel(attempt.question_type)}
                  </span>
                ) : null}
              </span>
              <span className="shrink-0 font-medium text-foreground">
                {attempt.score === null ? "In progress" : `${attempt.score.toFixed(0)}/100`}
              </span>
            </button>
          ))}
        </div>
      )}
    </CollapsiblePanel>
  );
}

// Persistent "why am I getting these questions" panel: overall stats, a
// mastery bar per topic, and the weakest subtopics the roulette in
// app/adaptive/selection.py is currently favoring. All of this comes from
// the same student-progress fetch the session already made for the
// "recent questions" strip -- nothing new to load.
function ProgressSidebar({ progress }: { progress: StudentProgressOut }) {
  // Highest weakness first: these are the subtopics most likely to be
  // picked next by the weighted roulette.
  const weakestSubtopics = useMemo(
    () => [...progress.subtopics].sort((left, right) => right.weakness - left.weakness).slice(0, 5),
    [progress.subtopics],
  );

  return (
    <Card className="border-border/70 bg-white/85">
      <CardContent className="divide-y divide-border/60 py-0">
        <div className="flex items-center gap-6 py-4 first:pt-5">
          <div>
            <div className="text-muted-foreground text-xs">Answered</div>
            <div className="font-heading font-semibold text-2xl text-foreground">
              {progress.answered}
            </div>
          </div>
          {progress.average_score !== null ? (
            <div>
              <div className="text-muted-foreground text-xs">Average score</div>
              <div className="font-heading font-semibold text-2xl text-foreground">
                {progress.average_score.toFixed(0)}
                <span className="ml-1 font-sans text-muted-foreground text-sm">/100</span>
              </div>
            </div>
          ) : null}
        </div>

        <div className="space-y-3 py-4">
          <div className="font-medium text-foreground text-sm">Topic mastery</div>
          {progress.topics.length === 0 ? (
            <p className="text-muted-foreground text-xs">
              Mastery appears here once a question has been scored.
            </p>
          ) : (
            progress.topics.map((topic) => (
              <div key={topic.topic_id} className="space-y-1.5">
                <div className="flex items-center justify-between gap-2 text-xs">
                  <span className="font-medium text-foreground">{topic.topic_name}</span>
                  <Badge
                    variant={topic.band === "high" ? "secondary" : "outline"}
                    className="text-[10px]"
                  >
                    {topic.band}
                  </Badge>
                </div>
                <Progress value={masteryPercent(topic.p_known)} className="h-1.5" />
              </div>
            ))
          )}
        </div>

        <div className="space-y-3 py-4 last:pb-5">
          <div>
            <div className="font-medium text-foreground text-sm">Focus areas</div>
            <p className="text-muted-foreground text-xs">
              What the adaptive engine is weighting most heavily for you right now.
            </p>
          </div>
          {weakestSubtopics.length === 0 ? (
            <p className="text-muted-foreground text-xs">No weak spots measured yet.</p>
          ) : (
            weakestSubtopics.map((subtopic) => (
              <div key={subtopic.subtopic_id} className="space-y-1.5">
                <div className="text-xs">
                  <span className="font-medium text-foreground">{subtopic.subtopic_name}</span>
                  <span className="text-muted-foreground"> · {subtopic.topic_name}</span>
                </div>
                <Progress value={weaknessPercent(subtopic.weakness)} className="h-1.5" />
              </div>
            ))
          )}
        </div>
      </CardContent>
    </Card>
  );
}

// The training loop itself: serve a question, take an answer, show the
// result, repeat. `result !== null` is what gates the served-question query
// off and the result card on -- there is deliberately no separate "phase"
// enum, since these two states already say the same thing.
export function StudentSessionScreen({ trainingSessionId }: { trainingSessionId: number }) {
  const router = useRouter();
  const session = useTrainingSession(trainingSessionId);
  const progress = useTrainingSessionProgress(trainingSessionId, {
    enabled: session.data !== undefined,
  });
  const endTrainingSession = useEndTrainingSession();
  const answerAttempt = useAnswerAttempt();
  const requestLiveQuestion = useRequestLiveQuestion();

  const [answer, setAnswer] = useState("");
  const [result, setResult] = useState<AnsweredOut | null>(null);
  // What was actually submitted, captured before `answer` is cleared for the
  // next question -- the result card needs it to show "your answer" next to
  // the correct one.
  const [lastAnswer, setLastAnswer] = useState("");
  const [selectedPastAttempt, setSelectedPastAttempt] = useState<AttemptOut | null>(null);

  const currentQuestion = useNextQuestion(trainingSessionId, {
    enabled: session.data?.ended_at === null && result === null,
  });
  const selectedPastQuestion = useAttemptReview(selectedPastAttempt?.id ?? null, {
    enabled: selectedPastAttempt !== null && selectedPastAttempt.score !== null,
  });
  // The just-answered question's full detail (answer key, reference
  // solution), fetched only once there is a result to show it alongside.
  const answeredQuestion = useAttemptReview(result?.attempt_id ?? null, {
    enabled: result !== null,
  });

  // A 404-shaped "nothing left to serve" -- a bank gap, or the student
  // finishing every topic in the curriculum -- is a state to render, not a
  // request failure -- every other query error still falls through to
  // QueryError below.
  const unavailable =
    currentQuestion.error instanceof ApiError &&
    (currentQuestion.error.code === "no_question_available" ||
      currentQuestion.error.code === "question_generating" ||
      currentQuestion.error.code === "curriculum_completed")
      ? currentQuestion.error
      : null;
  // Recent attempts scoped to this run, oldest first, capped to the last 10
  // so the strip doesn't grow unbounded across a long session.
  const sessionAttempts = useMemo(
    () =>
      (progress.data?.recent_attempts ?? [])
        .filter((attempt) => attempt.session_id === trainingSessionId)
        .sort((left, right) => left.ordinal - right.ordinal)
        .slice(-10),
    [progress.data?.recent_attempts, trainingSessionId],
  );
  // Only the answered ones are safe to revisit -- an open attempt is either
  // the current question or one still being scored.
  const revisitAttempts = useMemo(
    () => sessionAttempts.filter((attempt) => attempt.score !== null),
    [sessionAttempts],
  );
  const pendingCount = sessionAttempts.filter((attempt) => attempt.score === null).length;
  // Position of the open past-question sheet within this run's attempt list,
  // so its Previous/Next buttons can step through the same ordering the
  // "Recent questions" panel shows.
  const selectedPastIndex = useMemo(
    () => sessionAttempts.findIndex((attempt) => attempt.id === selectedPastAttempt?.id),
    [sessionAttempts, selectedPastAttempt],
  );
  const stepPastAttempt = (offset: number) => {
    if (selectedPastIndex < 0) return;
    const target = sessionAttempts[selectedPastIndex + offset];
    if (target) setSelectedPastAttempt(target);
  };
  // Consecutive strong answers (>=80) counting back from the most recent,
  // stopping at the first miss -- a running streak, not a lifetime best.
  const currentStreak = useMemo(() => {
    let streak = 0;
    for (let index = revisitAttempts.length - 1; index >= 0; index -= 1) {
      const score = revisitAttempts[index].score;
      if (score !== null && score >= 80) {
        streak += 1;
      } else {
        break;
      }
    }
    return streak;
  }, [revisitAttempts]);

  const submitAnswer = async () => {
    if (!currentQuestion.data || answer.trim().length === 0) return;
    // Capture before the mutation resolves: `answer` gets cleared for the
    // next question as soon as this succeeds, but the result card still
    // needs to know what was actually typed.
    const submitted = answer;
    try {
      const scored = await answerAttempt.mutateAsync({
        attemptId: currentQuestion.data.attempt_id,
        body: { answer: submitted },
      });
      setResult(scored);
      setLastAnswer(submitted);
      setAnswer("");
    } catch {
      // Mutation state renders the error.
    }
  };

  // "Next question": clear the result so the served-question query re-enables,
  // then force it to fetch immediately rather than waiting on cache staleness.
  const advance = () => {
    setResult(null);
    setAnswer("");
    void currentQuestion.refetch();
  };

  const endRun = async () => {
    try {
      await endTrainingSession.mutateAsync(trainingSessionId);
      router.push("/courses" as Route);
    } catch {
      // Mutation state renders the backend error.
    }
  };

  return (
    <>
      {session.isPending ? <TableSkeleton rows={4} /> : null}
      {session.isError ? <QueryError error={session.error} /> : null}

      {session.data ? (
        // Two columns at xl+ (question flow left, progress sidebar right,
        // sticky so it stays visible while scrolling a long prompt); a
        // single stacked column below that.
        <div className="mx-auto grid w-full max-w-6xl gap-5 pb-8 xl:grid-cols-[minmax(0,1fr)_18rem] xl:items-start">
          <PastQuestionSheet
            attempt={selectedPastAttempt}
            detail={selectedPastQuestion.data ?? null}
            isOpen={selectedPastAttempt !== null}
            onOpenChange={(open) => {
              if (!open) {
                setSelectedPastAttempt(null);
              }
            }}
            onPrev={() => stepPastAttempt(-1)}
            onNext={() => stepPastAttempt(1)}
            hasPrev={selectedPastIndex > 0}
            hasNext={selectedPastIndex >= 0 && selectedPastIndex < sessionAttempts.length - 1}
          />

          {/* Main column: run header, alerts, result, then the live question. */}
          <div className="flex min-w-0 flex-col gap-5">
            <section className="rounded-[1.25rem] border border-border/70 bg-white/86 px-5 py-5 shadow-[0_18px_40px_-34px_rgb(19_26_28_/_0.28)] sm:px-6">
              <div className="flex flex-col gap-5 lg:flex-row lg:items-start lg:justify-between">
                <div className="min-w-0 flex-1 space-y-4">
                  <div className="flex flex-wrap items-center gap-2">
                    <Badge variant="outline" className="rounded-full bg-background px-2.5 py-0.5">
                      Run #{session.data.id}
                    </Badge>
                    {currentStreak >= 2 ? (
                      <Badge className="gap-1 rounded-full bg-amber-100 px-2.5 py-0.5 text-amber-900 hover:bg-amber-100">
                        <Flame className="size-3.5" />
                        {currentStreak} in a row
                      </Badge>
                    ) : null}
                    <span className="text-muted-foreground text-sm">
                      Started {learnerDate(session.data.created_at)}
                    </span>
                  </div>

                  <div className="grid gap-4 md:grid-cols-[minmax(0,13rem)_minmax(0,1fr)] md:items-end">
                    <div className="space-y-1">
                      <div className="font-medium text-muted-foreground text-sm">
                        {session.data.student_name
                          ? `${session.data.student_name} — progress`
                          : "Session progress"}
                      </div>
                      <div className="font-heading font-semibold text-4xl text-foreground tracking-[-0.03em]">
                        {session.data.answered_count}
                        <span className="ml-2 font-medium font-sans text-base text-muted-foreground">
                          solved
                        </span>
                      </div>
                    </div>

                    <div className="space-y-2.5">
                      <div className="flex flex-wrap items-center justify-between gap-3">
                        <div className="font-medium text-foreground text-sm">
                          {session.data.set_label ?? `Set #${session.data.set_version_id ?? "?"}`}
                        </div>
                        <div className="text-muted-foreground text-sm">
                          {session.data.answered_count} solved
                          {pendingCount > 0
                            ? `, ${pendingCount} in progress`
                            : ", no pending question"}
                        </div>
                      </div>
                      <div className="flex flex-wrap items-center gap-4 text-muted-foreground text-xs">
                        <span>{session.data.served_count} served total</span>
                        <span>{session.data.answered_count} solved</span>
                        {pendingCount > 0 ? <span>{pendingCount} pending</span> : null}
                      </div>
                    </div>
                  </div>
                </div>
                <Button
                  type="button"
                  variant="outline"
                  onClick={() => void endRun()}
                  disabled={endTrainingSession.isPending || session.data.ended_at !== null}
                  className="rounded-full bg-white px-4 lg:self-start"
                >
                  End session
                </Button>
              </div>
            </section>

            {endTrainingSession.isError ? <QueryError error={endTrainingSession.error} /> : null}

            {session.data.ended_at ? (
              <Alert className="border-emerald-500/25 bg-white/80 shadow-[0_20px_44px_-34px_rgb(19_26_28_/_0.32)]">
                <CheckCircle2 />
                <AlertTitle>Session closed</AlertTitle>
                <AlertDescription>
                  This run ended on {learnerDate(session.data.ended_at)}.{" "}
                  <Link href="/courses">Return to the students page</Link>.
                </AlertDescription>
              </Alert>
            ) : null}

            {result ? (
              <ResultCard
                result={result}
                detail={answeredQuestion.data ?? null}
                submittedAnswer={lastAnswer}
                onNext={advance}
              />
            ) : null}
            {answerAttempt.isError ? <QueryError error={answerAttempt.error} /> : null}

            {unavailable?.code === "question_generating" ? (
              <Alert>
                <Loader2 className="animate-spin" />
                <AlertTitle>{unavailable.message}</AlertTitle>
                <AlertDescription>
                  {unavailable.detail ? <p>{unavailable.detail}</p> : null}
                  <p>It will appear here as soon as it is ready.</p>
                </AlertDescription>
              </Alert>
            ) : unavailable ? (
              <Alert>
                <AlertCircle />
                <AlertTitle>
                  {unavailable.code === "curriculum_completed"
                    ? "Curriculum completed"
                    : "Waiting for more questions"}
                </AlertTitle>
                <AlertDescription>
                  <p>{unavailable.message}</p>
                  {unavailable.detail ? <p>{unavailable.detail}</p> : null}
                  {unavailable.code === "no_question_available" ? (
                    <div className="space-y-2">
                      <p>This page checks for approved questions automatically.</p>
                      <div className="flex flex-wrap gap-2">
                        <Button
                          variant="outline"
                          size="sm"
                          disabled={currentQuestion.isFetching}
                          onClick={() => void currentQuestion.refetch()}
                        >
                          Check again
                        </Button>
                        <Button
                          size="sm"
                          disabled={requestLiveQuestion.isPending}
                          onClick={() => requestLiveQuestion.mutate(trainingSessionId)}
                        >
                          <Sparkles />
                          Make me a new question
                        </Button>
                      </div>
                    </div>
                  ) : null}
                </AlertDescription>
              </Alert>
            ) : null}

            {currentQuestion.isPending && result === null && !session.data.ended_at ? (
              <TableSkeleton rows={3} />
            ) : null}
            {currentQuestion.isError && unavailable === null ? (
              <QueryError error={currentQuestion.error} />
            ) : null}

            {currentQuestion.data && result === null ? (
              <Card className="overflow-hidden rounded-[2rem] border border-white/70 bg-[linear-gradient(180deg,rgba(255,255,255,0.98),rgba(247,250,249,0.92))] shadow-[0_30px_80px_-48px_rgb(19_26_28_/_0.45)]">
                <CardHeader className="gap-4 border-border/60 border-b px-6 py-6 sm:px-7">
                  <div className="flex flex-wrap items-center gap-2.5">
                    <CardTitle className="text-[1.9rem] leading-none tracking-[-0.03em]">
                      Question {currentQuestion.data.ordinal}
                    </CardTitle>
                    <Badge variant="outline" className="rounded-full bg-background/80 px-3 py-1">
                      {currentQuestion.data.served_difficulty}
                    </Badge>
                    {currentQuestion.data.question_type ? (
                      <Badge variant="outline" className="rounded-full bg-background/80 px-3 py-1">
                        {questionTypeLabel(currentQuestion.data.question_type)}
                      </Badge>
                    ) : null}
                    {currentQuestion.data.resumed ? (
                      <Badge
                        variant="outline"
                        className="rounded-full bg-amber-50 px-3 py-1 text-amber-900"
                      >
                        Resumed
                      </Badge>
                    ) : null}
                    {currentQuestion.data.live ? (
                      <Badge
                        variant="outline"
                        className="rounded-full bg-sky-50 px-3 py-1 text-sky-900"
                      >
                        <Sparkles className="size-3.5" />
                        Made for you
                      </Badge>
                    ) : null}
                  </div>
                  {currentQuestion.data.subtopic_name ? (
                    <div className="font-medium text-muted-foreground text-sm">
                      {currentQuestion.data.subtopic_name}
                    </div>
                  ) : null}
                </CardHeader>
                <CardContent className="space-y-5 px-6 py-6 sm:px-7">
                  <div className="space-y-4">
                    <div className="rounded-[1.5rem] border border-border/70 bg-white/80 p-5 shadow-[0_18px_40px_-34px_rgb(19_26_28_/_0.32)]">
                      <div className="mb-3 flex items-center justify-between gap-3">
                        <div className="font-medium text-[11px] text-muted-foreground uppercase tracking-[0.18em]">
                          Prompt
                        </div>
                        <ArrowUpRight className="size-4 text-muted-foreground" />
                      </div>
                      <div className="whitespace-pre-wrap text-[0.98rem] text-foreground leading-8">
                        {currentQuestion.data.prompt}
                      </div>
                    </div>

                    {currentQuestion.data.code ? (
                      <div className="overflow-hidden rounded-[1.5rem] border border-slate-900/85 bg-slate-950 shadow-[0_28px_60px_-36px_rgb(2_6_23_/_0.9)]">
                        <div className="flex items-center justify-between border-slate-800 border-b px-4 py-3">
                          <div className="font-medium text-[11px] text-slate-400 uppercase tracking-[0.18em]">
                            Reference code
                          </div>
                          <div className="flex items-center gap-1.5">
                            <span className="size-2 rounded-full bg-rose-400" />
                            <span className="size-2 rounded-full bg-amber-300" />
                            <span className="size-2 rounded-full bg-emerald-400" />
                          </div>
                        </div>
                        <pre className="overflow-x-auto p-4 font-mono text-slate-50 text-sm leading-7">
                          {currentQuestion.data.code}
                        </pre>
                      </div>
                    ) : null}
                  </div>

                  <AnswerForm
                    question={currentQuestion.data}
                    answer={answer}
                    onAnswerChange={setAnswer}
                    onSubmit={() => void submitAnswer()}
                    submitting={answerAttempt.isPending}
                  />
                </CardContent>
              </Card>
            ) : null}
          </div>

          {/* Sidebar column: omitted entirely until progress has loaded, rather
              than reserving its width with a skeleton. */}
          {progress.data ? (
            <div className="flex flex-col gap-4 xl:sticky xl:top-6">
              <RecentQuestionsPanel attempts={sessionAttempts} onSelect={setSelectedPastAttempt} />
              <ProgressSidebar progress={progress.data} />
            </div>
          ) : null}
        </div>
      ) : null}
    </>
  );
}
