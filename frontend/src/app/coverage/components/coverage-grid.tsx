"use client";

import { Loader2 } from "lucide-react";
import Link from "next/link";
import { QueryError } from "@/components/query-state";
import { Button } from "@/components/ui/button";
import { Tooltip, TooltipContent, TooltipTrigger } from "@/components/ui/tooltip";
import { useGenerateCoverageRun } from "@/lib/api/queries";
import type {
  CoverageReport,
  CoverageTargetRef,
  GenerationRunResponse,
  SubtopicCoverage,
  TopicCoverage,
} from "@/lib/api/types";
import { pluralise } from "@/lib/display";

type TopicHeatBand = "low" | "medium" | "high";

/** Every (subtopic, difficulty) cell of a topic still owed questions. */
function topicGapTargets(topic: TopicCoverage): CoverageTargetRef[] {
  return (topic.subtopics ?? []).flatMap((row) =>
    (row.cells ?? [])
      .filter((cell) => cell.needed > 0)
      .map((cell) => ({ subtopic_id: row.subtopic_id, difficulty: cell.difficulty })),
  );
}

function runSummaryLine(run: GenerationRunResponse): string {
  const offTopic = run.generated.filter((question) => !question.aim_matched).length;
  const parts = [`${run.generated.length} generated`];
  if (run.possible_duplicates > 0) {
    parts.push(pluralise(run.possible_duplicates, "possible duplicate"));
  }
  if (offTopic > 0) {
    parts.push(`${offTopic} on a different topic`);
  }
  if (run.failed.length > 0) {
    parts.push(`${run.failed.length} failed`);
  }
  return parts.join(" · ");
}

function subtopicQuestionCount(row: SubtopicCoverage): number {
  return (row.cells ?? []).reduce((total, cell) => total + cell.count, 0);
}

function coveredDifficultyCount(row: SubtopicCoverage): number {
  return (row.cells ?? []).filter((cell) => cell.count > 0).length;
}

function coveredSubtopicCount(topic: TopicCoverage): number {
  return (topic.subtopics ?? []).filter((row) => subtopicQuestionCount(row) > 0).length;
}

function coverageRatio(topic: TopicCoverage): number {
  const subtopicCount = topic.subtopics?.length ?? 0;
  if (subtopicCount === 0) return 0;
  return coveredSubtopicCount(topic) / subtopicCount;
}

function topicHeatBand(topic: TopicCoverage, minimumPerCell: number): TopicHeatBand {
  const subtopicCount = Math.max(topic.subtopics?.length ?? 0, 1);
  const ratio = topic.approved_questions / (subtopicCount * minimumPerCell);

  if (ratio >= 1.5) return "high";
  if (ratio >= 0.5) return "medium";
  return "low";
}

function topicQuestionTarget(topic: TopicCoverage, minimumPerCell: number): number {
  const subtopicCount = topic.subtopics?.length ?? 0;
  return subtopicCount * minimumPerCell;
}

function bandClasses(band: TopicHeatBand, covered: boolean): string {
  if (band === "high") {
    return covered
      ? "border-emerald-300/90 bg-emerald-400/85 dark:border-emerald-500/50 dark:bg-emerald-500/55"
      : "border-emerald-300/50 bg-emerald-400/15 dark:border-emerald-500/35 dark:bg-emerald-500/15";
  }
  if (band === "medium") {
    return covered
      ? "border-amber-300/90 bg-amber-400/85 dark:border-amber-500/50 dark:bg-amber-500/55"
      : "border-amber-300/50 bg-amber-400/15 dark:border-amber-500/35 dark:bg-amber-500/15";
  }
  return covered
    ? "border-red-300/90 bg-red-500/80 dark:border-red-500/50 dark:bg-red-500/55"
    : "border-red-300/50 bg-red-500/15 dark:border-red-500/35 dark:bg-red-500/15";
}

function bandLabel(band: TopicHeatBand): string {
  if (band === "high") return "Higher question volume in this topic";
  if (band === "medium") return "Moderate question volume in this topic";
  return "Lower question volume in this topic";
}

function volumeClasses(band: TopicHeatBand): string {
  if (band === "high") {
    return "border border-emerald-300/90 bg-emerald-400/10 text-emerald-700 dark:border-emerald-500/50 dark:bg-emerald-500/15 dark:text-emerald-300";
  }
  if (band === "medium") {
    return "border border-amber-300/90 bg-amber-400/10 text-amber-700 dark:border-amber-500/50 dark:bg-amber-500/15 dark:text-amber-300";
  }
  return "border border-red-300/90 bg-red-500/12 text-red-700 dark:border-red-500/50 dark:bg-red-500/15 dark:text-red-300";
}

function cardClasses(empty: boolean): string {
  if (empty) {
    return "rounded-xl border border-dashed border-border/70 bg-card/70 p-3";
  }
  return "rounded-xl border border-border/70 bg-card p-3";
}

function subtopicStatusLabel(row: SubtopicCoverage): string {
  const questionCount = subtopicQuestionCount(row);
  if (questionCount === 0) return "No questions yet";
  return `${questionCount} questions in this subtopic`;
}

function TopicSubtopicCell({
  row,
  topic,
  minimumPerCell,
}: {
  row: SubtopicCoverage;
  topic: TopicCoverage;
  minimumPerCell: number;
}) {
  const questionCount = subtopicQuestionCount(row);
  const difficultyCount = coveredDifficultyCount(row);
  const covered = questionCount > 0;
  const band = topicHeatBand(topic, minimumPerCell);
  const target = topicQuestionTarget(topic, minimumPerCell);

  return (
    <Tooltip>
      <TooltipTrigger asChild>
        <button
          type="button"
          className={`h-4 w-4 rounded-[5px] border transition-transform hover:scale-105 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-1 sm:h-[18px] sm:w-[18px] ${bandClasses(band, covered)}`}
          aria-label={`${row.subtopic_name} subtopic coverage in ${topic.topic_name}`}
          title={`${row.subtopic_name} · ${subtopicStatusLabel(row)}`}
        >
          <span className="sr-only">
            {row.subtopic_name}. {subtopicStatusLabel(row)}. {difficultyCount} of 3 difficulty
            levels have at least one question. Topic total: {topic.approved_questions} approved
            questions.
          </span>
        </button>
      </TooltipTrigger>
      <TooltipContent sideOffset={8} className="max-w-72">
        <div className="space-y-1">
          <p className="font-medium">{row.subtopic_name}</p>
          <p className="text-[11px] text-background/75">{topic.topic_name}</p>
          <p>{subtopicStatusLabel(row)}</p>
          <p>{difficultyCount} of 3 difficulty levels covered</p>
          <p>{bandLabel(band)}</p>
          <p>
            Topic total: {topic.approved_questions}/{target} questions
          </p>
        </div>
      </TooltipContent>
    </Tooltip>
  );
}

/** The topic card's Generate button, its pending state, and its inline result.
 *
 * `generatingElsewhere` covers the gap a local mutation can't: reload the page,
 * or navigate away and back, and this hook's `isPending` starts fresh at
 * `false` even though the server is still minutes into the run this topic's
 * last click started. Without it the button would look idle and invite a
 * second, overlapping run over the same gaps. */
function TopicGenerateButton({
  topic,
  generatingElsewhere,
}: {
  topic: TopicCoverage;
  generatingElsewhere: boolean;
}) {
  const targets = topicGapTargets(topic);
  const run = useGenerateCoverageRun();
  const generating = run.isPending || generatingElsewhere;

  return (
    <div className="mt-2 space-y-2">
      <div className="flex justify-end">
        <Button
          type="button"
          size="sm"
          variant="outline"
          className="h-7 rounded-full px-3 text-xs"
          aria-label={`Generate questions for ${topic.topic_name}`}
          disabled={targets.length === 0 || generating}
          onClick={() => run.mutate({ targets })}
        >
          {generating ? (
            <>
              <Loader2 className="size-3 animate-spin" />
              Generating…
            </>
          ) : (
            "Generate"
          )}
        </Button>
      </div>

      {run.data ? (
        <div className="rounded-lg border border-border/70 bg-muted/30 px-3 py-2 text-xs">
          <p>{runSummaryLine(run.data)}</p>
          <Link
            href={`/questions?run_id=${encodeURIComponent(run.data.run_id)}`}
            className="font-medium underline underline-offset-4"
          >
            Review these →
          </Link>
        </div>
      ) : null}

      {run.error ? <QueryError error={run.error} /> : null}
    </div>
  );
}

function Legend() {
  return (
    <div className="flex flex-wrap items-center gap-3 text-muted-foreground text-xs">
      <span className="font-medium text-foreground">1 square = 1 subtopic</span>
      <span className="inline-flex items-center gap-2">
        <span className="h-3 w-3 rounded-[4px] border border-red-300/90 bg-red-500/80" />
        Lower volume
      </span>
      <span className="inline-flex items-center gap-2">
        <span className="h-3 w-3 rounded-[4px] border border-amber-300/90 bg-amber-400/85" />
        Medium volume
      </span>
      <span className="inline-flex items-center gap-2">
        <span className="h-3 w-3 rounded-[4px] border border-emerald-300/90 bg-emerald-400/85" />
        Higher volume
      </span>
      <span className="inline-flex items-center gap-2">
        <span className="h-3 w-3 rounded-[4px] border border-border/70 bg-foreground/10" />
        Faded = no questions
      </span>
    </div>
  );
}

export function CoverageGrid({ report }: { report: CoverageReport }) {
  const topics = report.topics ?? [];
  const activeRunTopicIds = report.active_run_topic_ids ?? [];

  return (
    <div className="space-y-2">
      <section className="rounded-xl border border-border/70 bg-card p-3">
        <div className="flex flex-wrap items-center gap-2">
          <h2 className="font-medium text-sm">Topic coverage map</h2>
          <div className="rounded-full bg-muted px-2.5 py-0.5 font-mono text-[10px] tracking-[0.08em]">
            {topics.length} topics
          </div>
          <div className="rounded-full bg-muted px-2.5 py-0.5 font-mono text-[10px] tracking-[0.08em]">
            {report.question_count} questions
          </div>
        </div>
        <div className="mt-2 flex flex-wrap items-center gap-2">
          <Legend />
        </div>
      </section>

      <section className="grid gap-2 md:grid-cols-2 xl:grid-cols-3">
        {topics.map((topic) => {
          const subtopicCount = topic.subtopics?.length ?? 0;
          const coveredCount = coveredSubtopicCount(topic);
          const band = topicHeatBand(topic, report.minimum_per_cell);
          const target = topicQuestionTarget(topic, report.minimum_per_cell);
          const empty = coveredCount === 0;
          const ratio = coverageRatio(topic);

          return (
            <section key={topic.topic_id} className={cardClasses(empty)}>
              <div className="flex items-start justify-between gap-3">
                <div className="min-w-0">
                  <h3 className="truncate font-semibold text-sm">{topic.topic_name}</h3>
                  <p className="mt-1 text-muted-foreground text-xs">
                    {coveredCount}/{subtopicCount} subtopics
                  </p>
                </div>
                <div
                  className={`rounded-full px-2 py-0.5 font-mono text-[10px] ${volumeClasses(band)}`}
                >
                  {topic.approved_questions}/{target}
                </div>
              </div>
              <div className="mt-2 h-1 overflow-hidden rounded-full bg-muted">
                <div className="h-full bg-foreground/70" style={{ width: `${ratio * 100}%` }} />
              </div>
              <div className="mt-2 grid grid-cols-[repeat(auto-fill,minmax(18px,18px))] gap-1">
                {(topic.subtopics ?? []).map((row) => (
                  <TopicSubtopicCell
                    key={row.subtopic_id}
                    row={row}
                    topic={topic}
                    minimumPerCell={report.minimum_per_cell}
                  />
                ))}
              </div>
              <TopicGenerateButton
                topic={topic}
                generatingElsewhere={activeRunTopicIds.includes(topic.topic_id)}
              />
            </section>
          );
        })}
      </section>
    </div>
  );
}
