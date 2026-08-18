"use client";

import {
  closestCenter,
  DndContext,
  type DragEndEvent,
  KeyboardSensor,
  PointerSensor,
  useSensor,
  useSensors,
} from "@dnd-kit/core";
import {
  arrayMove,
  SortableContext,
  sortableKeyboardCoordinates,
  useSortable,
  verticalListSortingStrategy,
} from "@dnd-kit/sortable";
import { CSS } from "@dnd-kit/utilities";
import {
  AlertCircle,
  ArrowLeft,
  ArrowRight,
  ArrowRightToLine,
  ArrowUpRight,
  CheckCircle2,
  CircleDashed,
  GripVertical,
  XCircle,
} from "lucide-react";
import type { Route } from "next";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { useEffect, useMemo, useState } from "react";
import { QueryError, TableSkeleton } from "@/components/query-state";
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Progress } from "@/components/ui/progress";
import { Textarea } from "@/components/ui/textarea";
import { ApiError } from "@/lib/api/client";
import {
  useAnswerAttempt,
  useEndTrainingSession,
  useNextQuestion,
  useTrainingSession,
} from "@/lib/api/queries";
import type { AnsweredOut, ServedQuestionOut } from "@/lib/api/types";
import { cn } from "@/lib/utils";

function scoreTone(score: number) {
  if (score >= 100) return "success";
  if (score > 0) return "warn";
  return "error";
}

function formatResultLabel(score: number) {
  if (score >= 100) return "Correct";
  if (score > 0) return "Partly correct";
  return "Incorrect";
}

function resultIcon(score: number) {
  if (score >= 100) return CheckCircle2;
  if (score > 0) return CircleDashed;
  return XCircle;
}

function fallbackNotice(question: ServedQuestionOut) {
  if (!question.fallback_used) return null;
  return (
    <Alert>
      <AlertCircle />
      <AlertTitle>Difficulty fallback used</AlertTitle>
      <AlertDescription>
        Your measured mastery called for a <strong>{question.requested_difficulty}</strong>{" "}
        question, but this set only had a <strong>{question.served_difficulty}</strong> one
        available for this subtopic.
      </AlertDescription>
    </Alert>
  );
}

type ParsonsBlock = NonNullable<ServedQuestionOut["blocks"]>[number];

function toParsonsAnswer(blocks: ParsonsBlock[]) {
  return blocks.map((block) => `${"    ".repeat(block.indent)}${block.id}`).join("\n");
}

function parsonsIndentStyle(indent: number) {
  return {
    paddingLeft: `${indent * 1.4}rem`,
  };
}

function renderParsonsPreview(blocks: ParsonsBlock[]) {
  return blocks.map((block) => `${" ".repeat(block.indent * 4)}${block.text}`).join("\n");
}

function learnerDate(value: string) {
  return new Intl.DateTimeFormat(undefined, {
    dateStyle: "medium",
    timeStyle: "short",
  }).format(new Date(value));
}

function questionTypeLabel(questionType: ServedQuestionOut["question_type"]) {
  return questionType ? questionType.replace(/_/g, " ") : "";
}

function parseParsonsAnswer(blocks: ParsonsBlock[], answer: string) {
  const blockById = new Map(blocks.map((block) => [block.id, block]));
  const requestedLayout = answer
    .split(/\r?\n/)
    .map((line) => line.replace(/\t/g, "    "))
    .map((line) => {
      const trimmed = line.trim();
      if (!trimmed) return null;
      const leadingSpaces = line.length - line.trimStart().length;
      return {
        id: trimmed,
        indent: Math.max(0, Math.floor(leadingSpaces / 4)),
      };
    })
    .filter((item): item is { id: string; indent: number } => item !== null);
  const requestedSet = new Set(requestedLayout.map((item) => item.id));
  const ordered = requestedLayout
    .map((item) => {
      const block = blockById.get(item.id);
      return block ? { ...block, indent: item.indent } : null;
    })
    .filter((block): block is ParsonsBlock => Boolean(block));
  const remainder = blocks
    .filter((block) => !requestedSet.has(block.id))
    .map((block) => ({ ...block }));
  return [...ordered, ...remainder];
}

function SortableParsonsBlock({
  block,
  onIndentChange,
}: {
  block: ParsonsBlock;
  onIndentChange: (blockId: string, nextIndent: number) => void;
}) {
  const { attributes, listeners, setNodeRef, transform, transition, isDragging } = useSortable({
    id: block.id,
  });

  return (
    <div
      ref={setNodeRef}
      style={{
        transform: CSS.Transform.toString(transform),
        transition,
      }}
      className={cn(
        "group rounded-[0.95rem] border border-border bg-card/95",
        "transition duration-200",
        isDragging &&
          "scale-[1.015] border-primary/40 shadow-[0_20px_50px_-24px_rgb(19_26_28_/_0.35)]",
      )}
    >
      <button
        {...attributes}
        {...listeners}
        type="button"
        className={cn(
          "flex items-start gap-2.5 rounded-[0.95rem] px-2.5 py-2.5 text-left",
          "cursor-grab active:cursor-grabbing",
          "focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring/70",
        )}
        aria-label={`Move block ${block.id}`}
      >
        <div className="flex min-w-0 flex-1 items-start gap-3">
          <div className="mt-0.5 flex shrink-0 flex-col items-center">
            <div className="rounded-full bg-muted p-0.5 text-muted-foreground transition-colors group-hover:bg-accent group-hover:text-accent-foreground">
              <GripVertical className="size-3.5" />
            </div>
          </div>
          <div className="min-w-0 flex-1 space-y-1.5">
            <div className="flex flex-wrap items-center justify-between gap-1.5">
              <div className="flex flex-wrap items-center gap-2">
                <Badge
                  variant="outline"
                  className="h-5 rounded-md border-border bg-muted/50 px-1.5 font-mono text-[9px] text-muted-foreground"
                >
                  {block.id}
                </Badge>
                <span className="text-[11px] text-muted-foreground">Drag to reorder</span>
              </div>
              <div className="flex items-center gap-1">
                <button
                  type="button"
                  onClick={(event) => {
                    event.stopPropagation();
                    onIndentChange(block.id, Math.max(0, block.indent - 1));
                  }}
                  className="rounded-full border border-border bg-background p-0.5 text-muted-foreground transition hover:bg-accent hover:text-accent-foreground disabled:cursor-not-allowed disabled:opacity-45"
                  aria-label={`Outdent block ${block.id}`}
                  disabled={block.indent === 0}
                >
                  <ArrowLeft className="size-3" />
                </button>
                <div className="min-w-[4.5rem] rounded-full bg-muted px-2 py-0.5 text-center font-mono text-[9px] text-muted-foreground">
                  i{block.indent}
                </div>
                <button
                  type="button"
                  onClick={(event) => {
                    event.stopPropagation();
                    onIndentChange(block.id, block.indent + 1);
                  }}
                  className="rounded-full border border-border bg-background p-0.5 text-muted-foreground transition hover:bg-accent hover:text-accent-foreground"
                  aria-label={`Indent block ${block.id}`}
                >
                  <ArrowRightToLine className="size-3" />
                </button>
              </div>
            </div>
            <div
              className="overflow-x-auto rounded-[0.8rem] border border-border bg-muted/40 px-2.5 py-2"
              style={parsonsIndentStyle(block.indent)}
            >
              <pre className="whitespace-pre-wrap font-mono text-[12px] leading-5 text-foreground">
                {block.text}
              </pre>
            </div>
          </div>
        </div>
      </button>
    </div>
  );
}

function ParsonsComposer({
  question,
  answer,
  onAnswerChange,
}: {
  question: ServedQuestionOut;
  answer: string;
  onAnswerChange: (value: string) => void;
}) {
  const blocks = question.blocks ?? [];
  const [orderedBlocks, setOrderedBlocks] = useState<ParsonsBlock[]>(() =>
    parseParsonsAnswer(blocks, answer),
  );
  const sensors = useSensors(
    useSensor(PointerSensor, {
      activationConstraint: {
        distance: 8,
      },
    }),
    useSensor(KeyboardSensor, {
      coordinateGetter: sortableKeyboardCoordinates,
    }),
  );

  useEffect(() => {
    setOrderedBlocks(parseParsonsAnswer(blocks, answer));
  }, [blocks, answer]);

  const assembledAnswer = useMemo(() => toParsonsAnswer(orderedBlocks), [orderedBlocks]);

  useEffect(() => {
    if (assembledAnswer !== answer) {
      onAnswerChange(assembledAnswer);
    }
  }, [answer, assembledAnswer, onAnswerChange]);

  const handleDragEnd = (event: DragEndEvent) => {
    const { active, over } = event;
    if (!over || active.id === over.id) return;
    setOrderedBlocks((current) => {
      const oldIndex = current.findIndex((block) => block.id === active.id);
      const newIndex = current.findIndex((block) => block.id === over.id);
      if (oldIndex < 0 || newIndex < 0) return current;
      return arrayMove(current, oldIndex, newIndex);
    });
  };

  const resetOrder = () => {
    setOrderedBlocks(blocks);
  };

  const changeIndent = (blockId: string, nextIndent: number) => {
    setOrderedBlocks((current) =>
      current.map((block) =>
        block.id === blockId ? { ...block, indent: Math.max(0, nextIndent) } : block,
      ),
    );
  };

  if (blocks.length === 0) {
    return (
      <Alert variant="destructive">
        <AlertCircle />
        <AlertTitle>Blocks unavailable</AlertTitle>
        <AlertDescription>This Parsons question is missing its draggable blocks.</AlertDescription>
      </Alert>
    );
  }

  return (
    <div className="space-y-5">
      <div className="rounded-[1.5rem] border border-border bg-card/80 p-5 shadow-[0_18px_45px_-34px_rgb(19_26_28_/_0.38)] backdrop-blur-sm">
        <div className="flex flex-wrap items-start justify-between gap-4">
          <div className="space-y-2">
            <div className="flex flex-wrap items-center gap-2">
              <Badge className="bg-primary text-primary-foreground hover:bg-primary">
                Parsons puzzle
              </Badge>
              <Badge
                variant="outline"
                className="border-border bg-background/60 text-muted-foreground"
              >
                {orderedBlocks.length} blocks
              </Badge>
            </div>
            <div className="space-y-1">
              <h3 className="font-semibold text-base text-foreground">
                Build the solution in order
              </h3>
              <p className="max-w-2xl text-sm leading-6 text-muted-foreground">
                Rearrange each block until the code reads top to bottom. Drag up or down to reorder,
                then use the indent controls on each block to adjust nesting.
              </p>
            </div>
          </div>
          <Button
            type="button"
            variant="outline"
            onClick={resetOrder}
            className="border-border bg-background/60 text-foreground"
          >
            Reset order
          </Button>
        </div>
      </div>

      <div className="grid gap-5 xl:grid-cols-[minmax(0,1.25fr)_minmax(18rem,0.75fr)]">
        <div className="space-y-3">
          <div className="flex items-center justify-between gap-3 rounded-[1.15rem] border border-border bg-card/75 px-4 py-3">
            <div>
              <h4 className="font-medium text-sm text-foreground">Workspace</h4>
              <p className="text-xs text-muted-foreground">
                Arrange blocks from first line to last line.
              </p>
            </div>
            <div className="rounded-full bg-muted px-3 py-1 font-mono text-[11px] text-muted-foreground">
              {orderedBlocks.length} items
            </div>
          </div>
          <DndContext
            sensors={sensors}
            collisionDetection={closestCenter}
            onDragEnd={handleDragEnd}
          >
            <SortableContext
              items={orderedBlocks.map((block) => block.id)}
              strategy={verticalListSortingStrategy}
            >
              <div className="space-y-2">
                {orderedBlocks.map((block) => (
                  <SortableParsonsBlock
                    key={block.id}
                    block={block}
                    onIndentChange={changeIndent}
                  />
                ))}
              </div>
            </SortableContext>
          </DndContext>
        </div>

        <div className="space-y-4">
          <div className="rounded-[1.2rem] border border-border bg-card/80 p-4 shadow-[0_16px_32px_-28px_rgb(19_26_28_/_0.28)]">
            <div className="flex items-center justify-between gap-3">
              <div>
                <h4 className="font-medium text-sm text-foreground">Answer order</h4>
                <p className="text-xs text-muted-foreground">
                  Submitted automatically from the workspace.
                </p>
              </div>
              <Badge
                variant="outline"
                className="border-border bg-muted/40 font-mono text-[10px] text-muted-foreground"
              >
                ids
              </Badge>
            </div>
            <div className="mt-3 rounded-[0.95rem] border border-border bg-muted/40 p-3 font-mono text-[12px] leading-6 text-foreground">
              {assembledAnswer}
            </div>
          </div>

          <div className="rounded-[1.2rem] border border-border bg-card/80 p-4 shadow-[0_16px_32px_-28px_rgb(19_26_28_/_0.28)]">
            <div className="space-y-2">
              <h4 className="font-medium text-sm text-foreground">Code preview</h4>
              <p className="text-xs text-muted-foreground">
                A quick read of the program you are assembling.
              </p>
            </div>
            <pre className="mt-3 overflow-x-auto whitespace-pre-wrap rounded-[0.95rem] border border-border bg-muted/40 p-4 font-mono text-[13px] leading-6 text-foreground">
              {renderParsonsPreview(orderedBlocks)}
            </pre>
          </div>
        </div>
      </div>
    </div>
  );
}

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

  return (
    <div className="space-y-5">
      {question.question_type === "multiple_choice" && question.options ? (
        <fieldset className="space-y-3">
          <legend className="font-medium text-sm text-foreground">Choose one answer</legend>
          {question.options.map((option, index) => (
            <label
              key={`${question.attempt_id}-${option}`}
              className={cn(
                "group flex cursor-pointer items-start gap-3 rounded-[1.15rem] border p-4 transition-all duration-200",
                answer === String(index)
                  ? "border-primary/45 bg-primary/8 shadow-[0_16px_34px_-28px_rgb(20_91_84_/_0.55)]"
                  : "border-border/70 bg-card/75 hover:border-primary/30 hover:bg-white/90",
              )}
            >
              <input
                type="radio"
                name={`question-${question.attempt_id}`}
                value={index}
                checked={answer === String(index)}
                onChange={(event) => onAnswerChange(event.target.value)}
                className="mt-1 accent-[var(--accent-solid)]"
              />
              <div className="flex min-w-0 flex-1 items-start justify-between gap-3">
                <span className="text-sm leading-7 text-foreground">{option}</span>
                <span
                  className={cn(
                    "rounded-full px-2 py-1 font-mono text-[10px] uppercase tracking-[0.18em] transition-colors",
                    answer === String(index)
                      ? "bg-primary text-primary-foreground"
                      : "bg-muted text-muted-foreground group-hover:bg-accent group-hover:text-accent-foreground",
                  )}
                >
                  {String.fromCharCode(65 + index)}
                </span>
              </div>
            </label>
          ))}
        </fieldset>
      ) : question.question_type === "true_false" ? (
        <fieldset className="space-y-3">
          <legend className="font-medium text-sm text-foreground">True or false</legend>
          {[
            ["true", "True"],
            ["false", "False"],
          ].map(([value, label]) => (
            <label
              key={value}
              className={cn(
                "flex cursor-pointer items-center gap-3 rounded-[1.15rem] border p-4 transition-all duration-200",
                answer === value
                  ? "border-primary/45 bg-primary/8 shadow-[0_16px_34px_-28px_rgb(20_91_84_/_0.55)]"
                  : "border-border/70 bg-card/75 hover:border-primary/30 hover:bg-white/90",
              )}
            >
              <input
                type="radio"
                name={`question-${question.attempt_id}`}
                value={value}
                checked={answer === value}
                onChange={(event) => onAnswerChange(event.target.value)}
                className="accent-[var(--accent-solid)]"
              />
              <span className="text-sm font-medium text-foreground">{label}</span>
            </label>
          ))}
        </fieldset>
      ) : question.question_type === "parsons" ? (
        <ParsonsComposer question={question} answer={answer} onAnswerChange={onAnswerChange} />
      ) : (
        <div className="space-y-2">
          <label
            className="font-medium text-sm text-foreground"
            htmlFor={`answer-${question.attempt_id}`}
          >
            {question.question_type === "output_prediction" ? "Your answer" : "Your Python"}
          </label>
          <Textarea
            id={`answer-${question.attempt_id}`}
            value={answer}
            onChange={(event) => onAnswerChange(event.target.value)}
            rows={question.question_type === "output_prediction" ? 6 : 14}
            className="rounded-[1.2rem] border-border/80 bg-card/85 px-4 py-3 text-sm leading-7 shadow-[0_18px_40px_-34px_rgb(19_26_28_/_0.32)]"
            placeholder={
              question.question_type === "output_prediction"
                ? "Type the exact output"
                : "Write your answer here"
            }
          />
        </div>
      )}

      <div className="flex flex-col gap-3 rounded-[1.35rem] border border-border/70 bg-white/70 p-4 shadow-[0_18px_38px_-30px_rgb(19_26_28_/_0.26)] backdrop-blur-sm sm:flex-row sm:items-center sm:justify-between">
        <div className="space-y-1">
          <div className="font-medium text-sm text-foreground">Ready to submit?</div>
          <p className="text-sm text-muted-foreground">
            Review your response once, then lock it in and move to scoring.
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

function ResultCard({ result, onNext }: { result: AnsweredOut; onNext: () => void }) {
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
              <div className="font-heading text-4xl font-semibold tracking-[-0.03em] text-foreground">
                {result.score.toFixed(0)}
                <span className="ml-2 font-sans text-base font-medium text-muted-foreground">
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
          <div className="rounded-[1.1rem] border border-border/70 bg-muted/15 px-4 py-3">
            <div className="mb-2 text-[11px] font-medium uppercase tracking-[0.14em] text-muted-foreground">
              Feedback
            </div>
            <pre className="overflow-x-auto whitespace-pre-wrap text-sm leading-7 text-foreground">
              {result.detail}
            </pre>
          </div>
        ) : null}

        {result.mastery_before !== null && result.mastery_after !== null ? (
          <div className="space-y-2.5">
            <div className="flex items-center justify-between gap-3">
              <span className="font-medium text-foreground text-sm">Topic mastery</span>
              <span>
                {result.mastery_before.toFixed(3)} →{" "}
                <strong>{result.mastery_after.toFixed(3)}</strong>
              </span>
            </div>
            <Progress
              value={Math.max(0, Math.min(100, result.mastery_after * 100))}
              className="h-2"
            />
          </div>
        ) : null}

      </CardContent>
    </Card>
  );
}

export function StudentSessionScreen({ trainingSessionId }: { trainingSessionId: number }) {
  const router = useRouter();
  const session = useTrainingSession(trainingSessionId);
  const endTrainingSession = useEndTrainingSession();
  const answerAttempt = useAnswerAttempt();

  const [answer, setAnswer] = useState("");
  const [result, setResult] = useState<AnsweredOut | null>(null);

  const currentQuestion = useNextQuestion(trainingSessionId, {
    enabled: session.data?.ended_at === null && result === null,
  });

  const unavailable =
    currentQuestion.error instanceof ApiError &&
    currentQuestion.error.code === "no_question_available"
      ? currentQuestion.error
      : null;

  const submitAnswer = async () => {
    if (!currentQuestion.data || answer.trim().length === 0) return;
    try {
      const scored = await answerAttempt.mutateAsync({
        attemptId: currentQuestion.data.attempt_id,
        body: { answer },
      });
      setResult(scored);
      setAnswer("");
    } catch {
      // Mutation state renders the error.
    }
  };

  const advance = () => {
    setResult(null);
    setAnswer("");
    void currentQuestion.refetch();
  };

  const endRun = async () => {
    try {
      await endTrainingSession.mutateAsync(trainingSessionId);
      router.push("/students" as Route);
    } catch {
      // Mutation state renders the backend error.
    }
  };

  return (
    <>
      {session.isPending ? <TableSkeleton rows={4} /> : null}
      {session.isError ? <QueryError error={session.error} /> : null}

      {session.data ? (
        <div className="mx-auto flex w-full max-w-5xl flex-col gap-5 pb-8">
          <section className="rounded-[1.25rem] border border-border/70 bg-white/86 px-5 py-5 shadow-[0_18px_40px_-34px_rgb(19_26_28_/_0.28)] sm:px-6">
            <div className="flex flex-col gap-4 lg:flex-row lg:items-start lg:justify-between">
              <div className="space-y-3">
                <div className="flex flex-wrap items-center gap-2">
                  <Badge variant="outline" className="rounded-full bg-background px-2.5 py-0.5">
                    Run #{session.data.id}
                  </Badge>
                  <Badge variant="outline" className="rounded-full bg-background px-2.5 py-0.5">
                    {session.data.answered_count} answered
                  </Badge>
                  <span className="text-muted-foreground text-sm">
                    Started {learnerDate(session.data.created_at)}
                  </span>
                </div>
                <div className="space-y-1">
                  <div className="font-medium text-muted-foreground text-sm">
                    {session.data.student_name
                      ? `${session.data.student_name}'s workspace`
                      : "Training workspace"}
                  </div>
                  <h1 className="font-heading text-2xl font-semibold tracking-[-0.02em] text-foreground">
                    {session.data.set_label ?? `Set #${session.data.set_version_id ?? "?"}`}
                  </h1>
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
                <Link href="/students">Return to the students page</Link>.
              </AlertDescription>
            </Alert>
          ) : null}

          {result ? <ResultCard result={result} onNext={advance} /> : null}
          {answerAttempt.isError ? <QueryError error={answerAttempt.error} /> : null}

          {unavailable ? (
            <Alert>
              <AlertCircle />
              <AlertTitle>Nothing to serve</AlertTitle>
              <AlertDescription>
                <p>{unavailable.message}</p>
                {unavailable.detail ? <p>{unavailable.detail}</p> : null}
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
              <CardHeader className="gap-4 border-b border-border/60 px-6 py-6 sm:px-7">
                <div className="flex flex-wrap items-center gap-2.5">
                  <CardTitle className="text-[1.9rem] leading-none tracking-[-0.03em]">
                    Question {currentQuestion.data.ordinal}
                  </CardTitle>
                  <Badge variant="outline" className="rounded-full bg-background/80 px-3 py-1">
                    {currentQuestion.data.served_difficulty}
                  </Badge>
                  {currentQuestion.data.question_type ? (
                    <Badge
                      variant="outline"
                      className="rounded-full bg-background/80 px-3 py-1 capitalize"
                    >
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
                </div>
                <div className="flex flex-col gap-3 sm:flex-row sm:items-end sm:justify-between">
                  <div className="space-y-1.5">
                    {currentQuestion.data.subtopic_name ? (
                      <div className="text-sm font-medium text-muted-foreground">
                        {currentQuestion.data.subtopic_name}
                      </div>
                    ) : null}
                    <p className="max-w-2xl text-sm leading-7 text-muted-foreground">
                      Read the prompt carefully, then submit the strongest answer you can without
                      overthinking the interface.
                    </p>
                  </div>
                  <div className="rounded-[1rem] border border-border/60 bg-white/85 px-4 py-3 text-right shadow-[0_16px_34px_-30px_rgb(19_26_28_/_0.3)]">
                    <div className="text-[11px] font-medium uppercase tracking-[0.16em] text-muted-foreground">
                      Session progress
                    </div>
                    <div className="mt-1 font-heading text-2xl font-semibold tracking-[-0.03em] text-foreground">
                      {session.data.answered_count + 1}
                    </div>
                    <div className="text-xs text-muted-foreground">Current prompt position</div>
                  </div>
                </div>
              </CardHeader>
              <CardContent className="space-y-5 px-6 py-6 sm:px-7">
                {fallbackNotice(currentQuestion.data)}

                <div className="space-y-4">
                  <div className="rounded-[1.5rem] border border-border/70 bg-white/80 p-5 shadow-[0_18px_40px_-34px_rgb(19_26_28_/_0.32)]">
                    <div className="mb-3 flex items-center justify-between gap-3">
                      <div className="text-[11px] font-medium uppercase tracking-[0.18em] text-muted-foreground">
                        Prompt
                      </div>
                      <ArrowUpRight className="size-4 text-muted-foreground" />
                    </div>
                    <div className="whitespace-pre-wrap text-[0.98rem] leading-8 text-foreground">
                      {currentQuestion.data.prompt}
                    </div>
                  </div>

                  {currentQuestion.data.code ? (
                    <div className="overflow-hidden rounded-[1.5rem] border border-slate-900/85 bg-slate-950 shadow-[0_28px_60px_-36px_rgb(2_6_23_/_0.9)]">
                      <div className="flex items-center justify-between border-b border-slate-800 px-4 py-3">
                        <div className="text-[11px] font-medium uppercase tracking-[0.18em] text-slate-400">
                          Reference code
                        </div>
                        <div className="flex items-center gap-1.5">
                          <span className="size-2 rounded-full bg-rose-400" />
                          <span className="size-2 rounded-full bg-amber-300" />
                          <span className="size-2 rounded-full bg-emerald-400" />
                        </div>
                      </div>
                      <pre className="overflow-x-auto p-4 font-mono text-sm leading-7 text-slate-50">
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
      ) : null}
    </>
  );
}
