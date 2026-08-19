"use client";

import { RefreshCw, ScrollText, Sparkles, Trash2 } from "lucide-react";
import { toast } from "sonner";
import { PageHeader } from "@/components/page-header";
import { EmptyState, QueryError, TableSkeleton } from "@/components/query-state";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { ApiError } from "@/lib/api/client";
import {
  useDeleteInstructionRule,
  useInstructions,
  useRefreshInstruction,
} from "@/lib/api/queries";
import type { TypeInstruction } from "@/lib/api/types";

function occurrenceKeys(values: readonly string[]) {
  const seen = new Map<string, number>();
  return values.map((value) => {
    const next = (seen.get(value) ?? 0) + 1;
    seen.set(value, next);
    return `${value}::${next}`;
  });
}

function formatQuestionType(questionType: string) {
  return questionType
    .split("_")
    .map((part) => part.charAt(0).toUpperCase() + part.slice(1).toLowerCase())
    .join(" ");
}

function formatUpdatedAt(updatedAt: string | null) {
  if (!updatedAt) return "Never refreshed";
  return new Intl.DateTimeFormat(undefined, {
    month: "short",
    day: "numeric",
    year: "numeric",
  }).format(new Date(updatedAt));
}

function InstructionStatusBadges({ instruction }: { instruction: TypeInstruction }) {
  const staleBy = Math.max(0, instruction.available_reviews - instruction.review_count);

  return (
    <div className="flex flex-wrap items-center gap-2">
      <Badge variant={instruction.learned ? "secondary" : "outline"}>
        {instruction.learned ? "learned" : "default"}
      </Badge>
      {instruction.learned ? (
        <Badge variant={staleBy > 0 ? "outline" : "secondary"}>
          {staleBy > 0 ? `${staleBy} new review${staleBy === 1 ? "" : "s"}` : "up to date"}
        </Badge>
      ) : null}
      {instruction.rules.length > 0 ? (
        <Badge variant="outline">
          {instruction.rules.length} rule{instruction.rules.length === 1 ? "" : "s"}
        </Badge>
      ) : null}
    </div>
  );
}

function SummaryCard({
  title,
  value,
  hint,
  icon: Icon,
}: {
  title: string;
  value: number;
  hint: string;
  icon: typeof Sparkles;
}) {
  return (
    <Card className="review-panel">
      <CardHeader className="gap-3">
        <div className="flex items-start justify-between gap-3">
          <div>
            <div className="review-eyebrow">{title}</div>
            <CardTitle className="mt-2 text-3xl">{value}</CardTitle>
          </div>
          <div className="rounded-xl border border-border bg-muted p-2 text-muted-foreground">
            <Icon className="size-4" />
          </div>
        </div>
        <CardDescription>{hint}</CardDescription>
      </CardHeader>
    </Card>
  );
}

function InstructionCard({
  instruction,
  onRefresh,
  onDeleteRule,
  isRefreshing,
  deletingRuleIndex,
}: {
  instruction: TypeInstruction;
  onRefresh: (questionType: TypeInstruction["question_type"]) => void;
  onDeleteRule: (questionType: TypeInstruction["question_type"], ruleIndex: number) => void;
  isRefreshing: boolean;
  deletingRuleIndex: number | null;
}) {
  const canRefresh = instruction.available_reviews > 0;
  const isDeletingRule = deletingRuleIndex !== null;
  const ruleKeys = occurrenceKeys(instruction.rules);

  return (
    <Card className="review-panel h-full">
      <CardHeader className="gap-4">
        <div className="flex flex-wrap items-start justify-between gap-3">
          <div className="space-y-2">
            <div className="review-eyebrow">question type</div>
            <CardTitle className="flex items-center gap-2 text-lg">
              <ScrollText className="size-4 text-muted-foreground" />
              {formatQuestionType(instruction.question_type)}
            </CardTitle>
            <InstructionStatusBadges instruction={instruction} />
          </div>
          <Button
            variant="outline"
            size="sm"
            onClick={() => onRefresh(instruction.question_type)}
            disabled={!canRefresh || isRefreshing || isDeletingRule}
          >
            <RefreshCw className={isRefreshing ? "size-3.5 animate-spin" : "size-3.5"} />
            {isRefreshing ? "Refreshing" : "Refresh"}
          </Button>
        </div>
        <CardDescription className="flex flex-wrap gap-x-4 gap-y-1 text-xs">
          <span>{instruction.review_count} reviews used</span>
          <span>{instruction.available_reviews} reviews available</span>
          <span>updated {formatUpdatedAt(instruction.updated_at)}</span>
        </CardDescription>
      </CardHeader>
      <CardContent className="space-y-4">
        <div className="rounded-xl border border-border bg-muted/55 p-4">
          <p className="review-eyebrow mb-2">instruction</p>
          <p className="whitespace-pre-wrap text-foreground/90 text-sm leading-6">
            {instruction.instruction}
          </p>
        </div>

        <div className="space-y-2">
          <p className="review-eyebrow">learned rules</p>
          {instruction.rules.length > 0 ? (
            <ul className="space-y-2">
              {instruction.rules.map((rule, ruleIndex) => (
                <li
                  key={`${instruction.question_type}-${ruleKeys[ruleIndex]}`}
                  className="flex items-start justify-between gap-3 rounded-xl border border-border bg-background px-3 py-2 text-sm"
                >
                  <span className="flex-1">{rule}</span>
                  <Button
                    variant="ghost"
                    size="sm"
                    className="shrink-0"
                    onClick={() => onDeleteRule(instruction.question_type, ruleIndex)}
                    disabled={isRefreshing || isDeletingRule}
                  >
                    <Trash2 className="size-3.5" />
                    {deletingRuleIndex === ruleIndex ? "Deleting" : "Delete"}
                  </Button>
                </li>
              ))}
            </ul>
          ) : (
            <p className="rounded-xl border border-border border-dashed px-3 py-4 text-muted-foreground text-sm">
              No extracted rules yet. This type is still using the shipped base instruction.
            </p>
          )}
        </div>
      </CardContent>
    </Card>
  );
}

export default function InstructionsPage() {
  const { data, error, isPending } = useInstructions();
  const refreshInstruction = useRefreshInstruction();
  const deleteInstructionRule = useDeleteInstructionRule();

  const instructions = [...(data?.instructions ?? [])].sort((left, right) => {
    if (left.learned !== right.learned) return left.learned ? -1 : 1;
    if (left.available_reviews !== right.available_reviews) {
      return right.available_reviews - left.available_reviews;
    }
    return left.question_type.localeCompare(right.question_type);
  });

  const learnedCount = instructions.filter((instruction) => instruction.learned).length;
  const staleCount = instructions.filter(
    (instruction) =>
      instruction.learned && instruction.available_reviews > instruction.review_count,
  ).length;
  const refreshReadyCount = instructions.filter(
    (instruction) => instruction.available_reviews > 0,
  ).length;

  async function handleDeleteRule(
    questionType: TypeInstruction["question_type"],
    ruleIndex: number,
  ) {
    try {
      await deleteInstructionRule.mutateAsync({ questionType, ruleIndex });
      toast.success("Deleted learned rule", {
        description: "The instruction has been rebuilt from the remaining learned rules.",
      });
    } catch (error) {
      toast.error("Could not delete this learned rule", {
        description:
          error instanceof ApiError
            ? (error.detail ?? error.message)
            : error instanceof Error
              ? error.message
              : undefined,
      });
    }
  }

  return (
    <div className="space-y-6">
      <PageHeader
        title="Instructions"
        summary="See what the generator is told for each question type, which instructions were learned from reviews, and where fresh review outcomes are ready to be folded back in."
        actions={
          instructions.length > 0 ? (
            <>
              <Badge variant="secondary">{learnedCount} learned</Badge>
              <Badge variant="outline">{staleCount} stale</Badge>
            </>
          ) : null
        }
      />

      {error ? <QueryError error={error} /> : null}

      {isPending ? (
        <TableSkeleton rows={6} />
      ) : instructions.length === 0 ? (
        <EmptyState
          title="No instruction data yet"
          hint="The API returned no question-type instructions, so there is nothing to display."
        />
      ) : (
        <>
          <div className="grid gap-4 md:grid-cols-3">
            <SummaryCard
              title="Learned"
              value={learnedCount}
              hint="Question types already carrying review-derived instructions."
              icon={Sparkles}
            />
            <SummaryCard
              title="Need Refresh"
              value={staleCount}
              hint="Learned instructions with more reviews available than they currently use."
              icon={RefreshCw}
            />
            <SummaryCard
              title="Refresh Ready"
              value={refreshReadyCount}
              hint="Question types with at least one review available for learning."
              icon={ScrollText}
            />
          </div>

          <div className="grid gap-4 xl:grid-cols-2">
            {instructions.map((instruction) => (
              <InstructionCard
                key={instruction.question_type}
                instruction={instruction}
                onRefresh={(questionType) => refreshInstruction.mutate(questionType)}
                onDeleteRule={handleDeleteRule}
                isRefreshing={
                  refreshInstruction.isPending &&
                  refreshInstruction.variables === instruction.question_type
                }
                deletingRuleIndex={
                  deleteInstructionRule.isPending &&
                  deleteInstructionRule.variables?.questionType === instruction.question_type
                    ? deleteInstructionRule.variables.ruleIndex
                    : null
                }
              />
            ))}
          </div>
        </>
      )}
    </div>
  );
}
