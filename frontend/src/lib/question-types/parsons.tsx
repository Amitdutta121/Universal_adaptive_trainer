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
import { AlertCircle, ArrowLeft, ArrowRightToLine, GripVertical } from "lucide-react";
import { useEffect, useMemo, useState } from "react";
import {
  CodeBlock,
  MissingField,
} from "@/app/courses/[courseId]/review/components/review-primitives";
import {
  checkByName,
  presentBlocks,
  presentBlocksShuffled,
  presentStringArray,
} from "@/app/courses/[courseId]/review/review-utils";
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import type { ServedQuestionOut } from "@/lib/api/types";
import { cn } from "@/lib/utils";
import type {
  AnswerInputProps,
  AuthoringReviewProps,
  QuestionTypeUI,
  ReviewContentProps,
} from "./registry";
import { ExplanationPanel } from "./review-panels";

type ParsonsBlock = NonNullable<ServedQuestionOut["blocks"]>[number];

// Serializes a Parsons block order + indent back into the plain-text answer
// format the backend scorer expects (see `_parsons_layout` in scoring.py):
// one block id per line, indent encoded as four spaces per level.
function toParsonsAnswer(blocks: ParsonsBlock[]) {
  return blocks.map((block) => `${"    ".repeat(block.indent)}${block.id}`).join("\n");
}

// CSS nudge so a block's visual indent matches its logical indent level.
function parsonsIndentStyle(indent: number) {
  return {
    paddingLeft: `${indent * 1.4}rem`,
  };
}

// Renders a Parsons block sequence as the Python code it assembles into, so
// a student can read it as a program rather than a list of block ids.
function renderParsonsPreview(blocks: ParsonsBlock[]) {
  return blocks.map((block) => `${" ".repeat(block.indent * 4)}${block.text}`).join("\n");
}

// Rebuilds the correctly-ordered block list from the raw answer-key content
// (`content.blocks` for text/indent, `content.correct_order` for sequence),
// so it can be fed straight into `renderParsonsPreview`.
function parsonsCorrectBlocks(content: Record<string, unknown>): ParsonsBlock[] {
  const rawBlocks = Array.isArray(content.blocks)
    ? (content.blocks as Array<{ id?: unknown; text?: unknown; indent?: unknown }>)
    : [];
  const order = Array.isArray(content.correct_order) ? (content.correct_order as unknown[]) : [];
  const byId = new Map(
    rawBlocks
      .filter((block) => typeof block.id === "string")
      .map((block) => [block.id as string, block]),
  );
  return order
    .filter((id): id is string => typeof id === "string")
    .map((id) => byId.get(id))
    .filter((block): block is { id?: unknown; text?: unknown; indent?: unknown } => Boolean(block))
    .map((block) => ({
      id: String(block.id),
      text: typeof block.text === "string" ? block.text : "",
      indent: typeof block.indent === "number" ? block.indent : 0,
    }));
}

// The correctly-ordered Parsons solution, rendered as readable Python rather
// than a raw list of block ids.
function ParsonsReview({ content }: ReviewContentProps) {
  const blocks = parsonsCorrectBlocks(content);
  if (blocks.length === 0) return null;

  return (
    <div className="space-y-1">
      <div className="font-medium text-[11px] text-muted-foreground uppercase tracking-[0.14em]">
        Correct order
      </div>
      <pre className="overflow-x-auto whitespace-pre-wrap rounded-lg border border-border/70 bg-muted/20 p-3 font-mono text-foreground text-xs leading-6">
        {renderParsonsPreview(blocks)}
      </pre>
    </div>
  );
}

// Parses the plain-text answer buffer (one block id per line, leading
// whitespace as indent) back into ordered blocks, so the drag-and-drop
// composer can resume mid-session with whatever was last assembled. Blocks
// the buffer doesn't mention yet are appended at the end, unordered.
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

// One draggable block in the Parsons workspace: reorder by drag, or nudge
// indent level with the arrow buttons.
function SortableParsonsBlock({
  block,
  onIndentChange,
}: {
  block: ParsonsBlock;
  onIndentChange: (blockId: string, nextIndent: number) => void;
}) {
  const {
    attributes,
    listeners,
    setActivatorNodeRef,
    setNodeRef,
    transform,
    transition,
    isDragging,
  } = useSortable({
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
      <div className={cn("flex items-start gap-2.5 rounded-[0.95rem] px-2.5 py-2.5 text-left")}>
        <div className="flex min-w-0 flex-1 items-start gap-3">
          <div className="mt-0.5 flex shrink-0 flex-col items-center">
            <button
              {...attributes}
              {...listeners}
              ref={setActivatorNodeRef}
              type="button"
              className="cursor-grab rounded-full bg-muted p-0.5 text-muted-foreground transition-colors hover:bg-accent hover:text-accent-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring/70 active:cursor-grabbing"
              aria-label={`Move block ${block.id}`}
            >
              <GripVertical className="size-3.5" />
            </button>
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
              <pre className="whitespace-pre-wrap font-mono text-[12px] text-foreground leading-5">
                {block.text}
              </pre>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}

// Full Parsons puzzle UI: a draggable block list plus a live code preview.
// Owns its own ordering state so drag reflow feels instant, and syncs that
// state out to the parent's plain-text `answer` buffer (and back in, if the
// parent's buffer changes from under it, e.g. on session resume).
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
      {/* A plain instruction line, not a card -- the question header already
          carries a "Parsons" type badge and the Prompt block above already
          states the task, so giving this its own bordered/shadowed card made
          it read as a second, competing question. */}
      <div className="flex flex-wrap items-center justify-between gap-3 text-muted-foreground text-sm">
        <p>Drag blocks up or down to reorder, then use the indent controls to adjust nesting.</p>
        <Button type="button" variant="ghost" size="sm" onClick={resetOrder}>
          Reset order
        </Button>
      </div>

      <div className="grid gap-5 xl:grid-cols-[minmax(0,1.25fr)_minmax(18rem,0.75fr)]">
        <div className="space-y-3">
          <div className="flex items-center justify-between gap-3 rounded-[1.15rem] border border-border bg-card/75 px-4 py-3">
            <div>
              <h4 className="font-medium text-foreground text-sm">Workspace</h4>
              <p className="text-muted-foreground text-xs">
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
                <h4 className="font-medium text-foreground text-sm">Answer order</h4>
                <p className="text-muted-foreground text-xs">
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
            <div className="mt-3 rounded-[0.95rem] border border-border bg-muted/40 p-3 font-mono text-[12px] text-foreground leading-6">
              {assembledAnswer}
            </div>
          </div>

          <div className="rounded-[1.2rem] border border-border bg-card/80 p-4 shadow-[0_16px_32px_-28px_rgb(19_26_28_/_0.28)]">
            <div className="space-y-2">
              <h4 className="font-medium text-foreground text-sm">Code preview</h4>
              <p className="text-muted-foreground text-xs">
                A quick read of the program you are assembling.
              </p>
            </div>
            <pre className="mt-3 overflow-x-auto whitespace-pre-wrap rounded-[0.95rem] border border-border bg-muted/40 p-4 font-mono text-[13px] text-foreground leading-6">
              {renderParsonsPreview(orderedBlocks)}
            </pre>
          </div>
        </div>
      </div>
    </div>
  );
}

function ParsonsAnswerInput({ question, value, onChange }: AnswerInputProps) {
  return <ParsonsComposer question={question} answer={value} onAnswerChange={onChange} />;
}

function ParsonsAuthoringReview({ detail }: AuthoringReviewProps) {
  const checks = detail.validation_checks;
  const content = detail.content ?? {};
  const blocks = presentBlocks(content.blocks);
  const shuffledBlocks = presentBlocksShuffled(content.blocks, detail.question.id);
  const order = presentStringArray(content.correct_order) ?? [];
  const compiled = checkByName(checks, "parsons_reference_compiles");
  const assembled =
    blocks && order.length
      ? order
          .map((id) => blocks.find((block) => block.id === id))
          .filter((block): block is NonNullable<typeof block> => Boolean(block))
          .map((block) => `${" ".repeat(block.indent * 4)}${block.text}`)
          .join("\n")
      : null;
  return (
    <div className="space-y-4">
      <div className="grid gap-4 xl:grid-cols-2">
        <Card className="review-panel border">
          <CardHeader>
            <CardTitle>Blocks</CardTitle>
            <CardDescription>The student sees these shuffled.</CardDescription>
          </CardHeader>
          <CardContent className="space-y-2">
            {shuffledBlocks ? (
              shuffledBlocks.map((block) => (
                <div
                  key={block.id}
                  className="review-panel-muted whitespace-pre-wrap rounded-[0.7rem] border px-3 py-2 font-mono text-xs"
                >
                  {`${" ".repeat(block.indent * 4)}${block.text}`}
                </div>
              ))
            ) : (
              <MissingField label="Blocks are missing." />
            )}
          </CardContent>
        </Card>
        <Card className="review-panel border">
          <CardHeader>
            <CardTitle>Assembled in canonical order</CardTitle>
            <CardDescription>
              {compiled?.passed
                ? "Reconstruction compiles."
                : "Reconstruction or compilation failed."}
            </CardDescription>
          </CardHeader>
          <CardContent className="space-y-3">
            {assembled ? (
              <CodeBlock>{assembled}</CodeBlock>
            ) : (
              <MissingField label="Correct order is missing." />
            )}
            {compiled?.evidence ? (
              <Alert variant="destructive">
                <AlertCircle />
                <AlertTitle>Compile evidence</AlertTitle>
                <AlertDescription>
                  <p className="whitespace-pre-wrap font-mono text-xs">{compiled.evidence}</p>
                </AlertDescription>
              </Alert>
            ) : null}
          </CardContent>
        </Card>
      </div>
      <ExplanationPanel detail={detail} />
    </div>
  );
}

export const parsons: QuestionTypeUI = {
  kind: "testable_program",
  label: "Parsons",
  shortLabel: "Parsons",
  answerLabel: "Answer order",
  AnswerInput: ParsonsAnswerInput,
  ReviewContent: ParsonsReview,
  AuthoringReview: ParsonsAuthoringReview,
};
