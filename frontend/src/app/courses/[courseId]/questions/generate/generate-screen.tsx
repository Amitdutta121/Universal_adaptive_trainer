"use client";

/**
 * Generate from book chunks — the spec sheet.
 *
 * Every chunk in every imported book on one row, with what it should produce: how
 * many easy, medium and hard questions, and which formats they are drawn from.
 * Reading a chunk and specifying it are the same screen, because deciding a chunk
 * can carry two hard coding questions needs the chunk in front of you.
 *
 * The composition is the whole of this file. Filters live in the URL (`nuqs`), the
 * unsubmitted sheet lives in React state (`useChunkSpecs`), the chunks and the
 * price of the sheet come from the API (`useSheetRows`, `useBatchPlan`), and every
 * piece of the layout is its own component under `components/`.
 */

import { parseAsInteger, parseAsString, parseAsStringLiteral, useQueryState } from "nuqs";
import { useEffect, useMemo, useState } from "react";
import { PageHeader } from "@/components/page-header";
import { EmptyState, QueryError, TableSkeleton } from "@/components/query-state";
import { Badge } from "@/components/ui/badge";
import { isActive } from "@/components/jobs/job-display";
import { useApprovedCurriculum, useBatchPlan, useGenerateBatch, useJobs } from "@/lib/api/queries";
import type { QuestionType } from "@/lib/api/types";
import { ChunkPreview } from "./components/chunk-preview";
import { RunJobStatus } from "./components/run-job-status";
import { RunSummary } from "./components/run-summary";
import { SheetToolbar } from "./components/sheet-toolbar";
import { SpecSheet } from "./components/spec-sheet";
import { type SheetRow, toRequestChunks } from "./spec-sheet-types";
import { useCourseQuestionTypes } from "./use-course-question-types";
import { useChunkSpecs } from "./use-chunk-specs";
import { useDebouncedValue } from "./use-debounced-value";
import { type SheetFilters, useSheetRows } from "./use-sheet-rows";

const PRODUCED_FILTERS = ["any", "none"] as const;

/** What an untouched row asks for until the professor says otherwise. */
const INITIAL_DEFAULT_FORMATS: QuestionType[] = ["multiple_choice"];

export function GenerateScreen() {
  const [bookId, setBookId] = useQueryState("book", parseAsInteger);
  const [chapterId, setChapterId] = useQueryState("chapter", parseAsInteger);
  const [produced, setProduced] = useQueryState(
    "produced",
    parseAsStringLiteral(PRODUCED_FILTERS).withDefault("any"),
  );
  const [search, setSearch] = useQueryState("q", parseAsString.withDefault(""));

  const [defaultFormats, setDefaultFormats] = useState<QuestionType[]>(INITIAL_DEFAULT_FORMATS);
  // A course that did not choose multiple choice starts from the first type it did choose.
  const offered = useCourseQuestionTypes();
  useEffect(() => {
    setDefaultFormats((current) => {
      const kept = current.filter((format) => offered.includes(format));
      if (kept.length === current.length) return current;
      return kept.length > 0 ? kept : offered.slice(0, 1);
    });
  }, [offered]);
  const [reading, setReading] = useState<SheetRow | null>(null);

  const filters: SheetFilters = useMemo(
    () => ({ bookId, chapterId, produced, search }),
    [bookId, chapterId, produced, search],
  );

  const approvedCurriculum = useApprovedCurriculum();
  const sheet = useSheetRows(filters);
  const specs = useChunkSpecs();
  const generate = useGenerateBatch();
  // The run is a background job. Follow the one this page started; after a reload or a
  // return to this page, follow the newest bulk run still in flight instead.
  const [startedJobId, setStartedJobId] = useState<string | null>(null);
  const jobs = useJobs();
  const followedId =
    startedJobId ??
    jobs.data?.jobs.find((job) => job.kind === "bulk_generation" && isActive(job))?.id ??
    null;
  const runJob = jobs.data?.jobs.find((job) => job.id === followedId);
  const isRunning = generate.isPending || (runJob ? isActive(runJob) : startedJobId !== null);

  // Priced against every chunk, not only the visible ones: narrowing a filter
  // must not quietly drop rows from the run that is about to be paid for.
  const requestChunks = useMemo(
    () => toRequestChunks(sheet.allRows, specs.specs, defaultFormats),
    [sheet.allRows, specs.specs, defaultFormats],
  );
  const settledChunks = useDebouncedValue(requestChunks);
  const plan = useBatchPlan(settledChunks);

  const applyFilters = (patch: Partial<SheetFilters>) => {
    if ("bookId" in patch) void setBookId(patch.bookId ?? null);
    if ("chapterId" in patch) void setChapterId(patch.chapterId ?? null);
    if (patch.produced) void setProduced(patch.produced);
    if (patch.search !== undefined) void setSearch(patch.search);
  };

  const runBatch = () => {
    if (requestChunks.length === 0) return;
    generate.mutate(
      {
        curriculum_version_id: approvedCurriculum.data?.version.id ?? null,
        chunks: requestChunks,
      },
      { onSuccess: (started) => setStartedJobId(started.job_id) },
    );
  };

  return (
    <>
      <PageHeader
        title="Generate from chunks"
        summary="Set what each textbook chunk should produce, across every book, then run it once."
        actions={
          <Badge variant="outline" className="h-7 rounded-full px-3 font-mono tracking-[0.08em]">
            {sheet.allRows.length} chunks
          </Badge>
        }
      />

      <section className="space-y-4">
        {generate.isError ? <QueryError error={generate.error} /> : null}
        {runJob ? <RunJobStatus job={runJob} onRetried={setStartedJobId} /> : null}
        {approvedCurriculum.isError ? <QueryError error={approvedCurriculum.error} /> : null}

        <div className="rounded-[1.4rem] border border-border/70 bg-[linear-gradient(135deg,rgba(243,248,246,0.96),rgba(255,255,255,0.88))] p-5 shadow-[0_16px_38px_-32px_rgba(19,26,28,0.55)] dark:bg-[linear-gradient(135deg,rgba(20,30,28,0.96),rgba(16,22,24,0.88))]">
          <div className="flex flex-col gap-3 md:flex-row md:items-start md:justify-between">
            <div className="space-y-1.5">
              <p className="font-mono text-[0.67rem] text-muted-foreground uppercase tracking-[0.16em]">
                Generation taxonomy
              </p>
              {approvedCurriculum.data ? (
                <>
                  <p className="font-heading text-foreground text-xl tracking-[-0.025em]">
                    {approvedCurriculum.data.version.label}
                  </p>
                  <p className="text-muted-foreground text-sm leading-6">
                    Every generated question is grounded in approved curriculum version{" "}
                    <span className="font-mono text-foreground">
                      {approvedCurriculum.data.version.id}
                    </span>
                    . Change the taxonomy from the header selector above; this screen then generates
                    against that taxonomy.
                  </p>
                  <p className="text-muted-foreground text-sm leading-6">
                    Topic and subtopics are inferred from the source chunk during generation, then
                    checked against this taxonomy.
                  </p>
                </>
              ) : (
                <p className="text-muted-foreground text-sm leading-6">
                  No approved taxonomy is available yet. Upload and approve one before generating
                  questions.
                </p>
              )}
            </div>

            {approvedCurriculum.data ? (
              <Badge
                variant="outline"
                className="h-7 w-fit rounded-full px-3 font-mono tracking-[0.08em]"
              >
                version {approvedCurriculum.data.version.id}
              </Badge>
            ) : null}
          </div>
        </div>

        <div className="overflow-hidden rounded-[1.4rem] border border-border/70 bg-background/70 shadow-[0_20px_45px_-32px_rgba(19,26,28,0.55)]">
          <SheetToolbar
            books={sheet.books}
            chapters={sheet.chapters}
            filters={filters}
            onFilterChange={applyFilters}
            defaultFormats={defaultFormats}
            onDefaultFormatsChange={setDefaultFormats}
            selectedCount={specs.selectedIds.size}
            onFill={specs.fillSelected}
            onClearAll={specs.clearAll}
          />

          {sheet.isError ? (
            <div className="p-5">
              <QueryError error={sheet.error} />
            </div>
          ) : null}

          {sheet.isPending ? (
            <div className="p-5">
              <TableSkeleton />
            </div>
          ) : null}

          {!sheet.isPending && !sheet.isError && sheet.rows.length === 0 ? (
            <div className="p-5">
              <EmptyState
                title="No chunks match this filter"
                hint={
                  sheet.allRows.length === 0
                    ? "Import a book first — a chunk is one instructional section of one."
                    : "Broaden the book, chapter or search filters."
                }
              />
            </div>
          ) : null}

          {!sheet.isPending && sheet.rows.length > 0 ? (
            <SpecSheet
              rows={sheet.rows}
              specFor={specs.specFor}
              defaultFormats={defaultFormats}
              selectedIds={specs.selectedIds}
              readingSectionId={reading?.sectionId ?? null}
              onToggleSelected={specs.toggleSelected}
              onSelectAllVisible={(selected) =>
                specs.selectMany(
                  sheet.rows.map((row) => row.sectionId),
                  selected,
                )
              }
              onRead={setReading}
              onCountChange={specs.setCount}
              onFormatsChange={specs.setFormats}
            />
          ) : null}

          <ChunkPreview row={reading} onClose={() => setReading(null)} />

          <RunSummary
            totals={plan.data?.totals ?? null}
            isPricing={plan.isFetching}
            isRunning={isRunning}
            canRun={Boolean(approvedCurriculum.data)}
            onRun={runBatch}
          />
        </div>
      </section>
    </>
  );
}
