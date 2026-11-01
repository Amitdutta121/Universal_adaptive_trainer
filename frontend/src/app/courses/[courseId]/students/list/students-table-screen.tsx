"use client";

/**
 * Every learner as one flat table. Laid out like the Questions bank (search,
 * filter buttons, "Active view" strip, striped table, footer) and filtered
 * server-side by the same filters as Roster.
 */

import { ArrowDown, ArrowUp, ArrowUpDown, Search } from "lucide-react";
import { useEffect, useState } from "react";
import { PageHeader } from "@/components/page-header";
import { EmptyState, QueryError, TableSkeleton } from "@/components/query-state";
import { ActiveFilterChip, FilterLabel, FilterSelect } from "@/components/table-filters";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import { useApprovedCurriculum, useCurriculumVersions, useStudents } from "@/lib/api/queries";

const PAGE_SIZE = 25;

type ScoreFilter = "all" | "lt50" | "50to70" | "70to85" | "85plus";
type AnsweredFilter = "all" | "0" | "1to5" | "6to20" | "21plus";
type ActivityFilter = "all" | "today" | "last7" | "last30" | "inactive";
type SortKey = "name" | "email" | "answered" | "average" | "last_active" | "enrolled";
type SortOrder = "asc" | "desc";

const SCORE_OPTIONS: { value: ScoreFilter; label: string }[] = [
  { value: "all", label: "All" },
  { value: "lt50", label: "Below 50" },
  { value: "50to70", label: "50 to 69" },
  { value: "70to85", label: "70 to 84" },
  { value: "85plus", label: "85 and above" },
];

const ANSWERED_OPTIONS: { value: AnsweredFilter; label: string }[] = [
  { value: "all", label: "All" },
  { value: "0", label: "None" },
  { value: "1to5", label: "1 to 5" },
  { value: "6to20", label: "6 to 20" },
  { value: "21plus", label: "21+" },
];

const ACTIVITY_OPTIONS: { value: ActivityFilter; label: string }[] = [
  { value: "all", label: "All" },
  { value: "today", label: "Today" },
  { value: "last7", label: "Last 7 days" },
  { value: "last30", label: "Last 30 days" },
  { value: "inactive", label: "Inactive" },
];

const HEAD_CLASS =
  "border-border/80 border-b bg-muted/30 py-3 text-[0.72rem] text-muted-foreground uppercase tracking-[0.14em]";

function formatDate(value: string | null, withTime = true) {
  if (!value) return "-";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return value;
  return new Intl.DateTimeFormat("en-US", {
    year: "numeric",
    month: "short",
    day: "2-digit",
    ...(withTime ? { hour: "2-digit", minute: "2-digit" } : {}),
  }).format(date);
}

/** The date in the cell, the full timestamp on hover, as on Questions. */
function DateCell({ value }: { value: string | null }) {
  return (
    <span className="whitespace-nowrap text-muted-foreground text-xs" title={formatDate(value)}>
      {formatDate(value, false)}
    </span>
  );
}

/**
 * A column title that sorts the whole roster on the server. Same button as the
 * Questions bank's sortable headers; the arrow shows the current direction.
 */
function SortableHead({
  label,
  column,
  sort,
  order,
  onSort,
  numeric = false,
}: {
  label: string;
  column: SortKey;
  sort: SortKey | null;
  order: SortOrder;
  onSort: (column: SortKey) => void;
  numeric?: boolean;
}) {
  const active = sort === column;
  const Icon = !active ? ArrowUpDown : order === "asc" ? ArrowUp : ArrowDown;
  return (
    <TableHead
      className={`${HEAD_CLASS} ${numeric ? "text-right" : ""}`}
      aria-sort={active ? (order === "asc" ? "ascending" : "descending") : "none"}
    >
      <Button
        variant="ghost"
        size="sm"
        className={`font-medium text-[0.72rem] uppercase tracking-[0.14em] hover:text-foreground ${
          numeric ? "-mr-3" : "-ml-3"
        } ${active ? "text-foreground" : "text-muted-foreground"}`}
        onClick={() => onSort(column)}
      >
        {label} <Icon className="size-3" />
      </Button>
    </TableHead>
  );
}

function optionLabel<T extends string>(options: { value: T; label: string }[], value: T) {
  return options.find((option) => option.value === value)?.label ?? value;
}

export function StudentsTableScreen() {
  const [searchInput, setSearchInput] = useState("");
  const [searchTerm, setSearchTerm] = useState("");
  const [scoreFilter, setScoreFilter] = useState<ScoreFilter>("all");
  const [answeredFilter, setAnsweredFilter] = useState<AnsweredFilter>("all");
  const [activityFilter, setActivityFilter] = useState<ActivityFilter>("all");
  const [curriculumFilter, setCurriculumFilter] = useState<string>("all");
  const [page, setPage] = useState(1);
  const [sort, setSort] = useState<SortKey | null>(null);
  const [order, setOrder] = useState<SortOrder>("asc");

  // A new column starts ascending; clicking the sorted column flips it.
  function toggleSort(column: SortKey) {
    setOrder(sort === column && order === "asc" ? "desc" : "asc");
    setSort(column);
    setPage(1);
  }

  // Debounce the search box so a keystroke is not a request; a settled term restarts at page 1.
  useEffect(() => {
    const timer = setTimeout(() => {
      setSearchTerm(searchInput.trim());
      setPage(1);
    }, 250);
    return () => clearTimeout(timer);
  }, [searchInput]);

  function pickFilter<T>(set: (value: T) => void, value: T) {
    set(value);
    setPage(1);
  }

  const curriculumVersions = useCurriculumVersions();
  const approvedCurriculum = useApprovedCurriculum();
  const activeVersionId = approvedCurriculum.data?.version.id ?? null;

  // Follow the app's active taxonomy by default, as Roster does.
  useEffect(() => {
    if (activeVersionId !== null) {
      setCurriculumFilter(String(activeVersionId));
      setPage(1);
    }
  }, [activeVersionId]);

  const taxonomyOptions = [
    { value: "all", label: "All" },
    ...(curriculumVersions.data?.versions ?? []).map((version) => ({
      value: String(version.id),
      label: version.label,
    })),
  ];

  const list = useStudents({
    search: searchTerm,
    score: scoreFilter,
    answered: answeredFilter,
    activity: activityFilter,
    curriculumVersionId: curriculumFilter === "all" ? null : Number(curriculumFilter),
    page,
    pageSize: PAGE_SIZE,
    sort,
    order,
  });

  const rows = list.data?.students ?? [];
  const total = list.data?.total ?? 0;
  const pageSize = list.data?.page_size ?? PAGE_SIZE;
  const pageCount = Math.max(1, Math.ceil(total / pageSize));

  const activeFilters = [
    searchTerm
      ? { label: "search", value: searchTerm, onClear: () => setSearchInput("") }
      : null,
    scoreFilter !== "all"
      ? {
          label: "score",
          value: optionLabel(SCORE_OPTIONS, scoreFilter),
          onClear: () => pickFilter(setScoreFilter, "all" as ScoreFilter),
        }
      : null,
    answeredFilter !== "all"
      ? {
          label: "answered",
          value: optionLabel(ANSWERED_OPTIONS, answeredFilter),
          onClear: () => pickFilter(setAnsweredFilter, "all" as AnsweredFilter),
        }
      : null,
    activityFilter !== "all"
      ? {
          label: "active",
          value: optionLabel(ACTIVITY_OPTIONS, activityFilter),
          onClear: () => pickFilter(setActivityFilter, "all" as ActivityFilter),
        }
      : null,
    curriculumFilter !== "all"
      ? {
          label: "taxonomy",
          value: optionLabel(taxonomyOptions, curriculumFilter),
          onClear: () => pickFilter(setCurriculumFilter, "all"),
        }
      : null,
  ].filter((value): value is NonNullable<typeof value> => value !== null);

  const isFiltered = activeFilters.length > 0;
  const sortProps = { sort, order, onSort: toggleSort };

  function clearFilters() {
    setSearchInput("");
    setSearchTerm("");
    setScoreFilter("all");
    setAnsweredFilter("all");
    setActivityFilter("all");
    setCurriculumFilter("all");
    setPage(1);
  }

  return (
    <>
      <PageHeader
        title="Students"
        summary="Every enrolled learner in one table. Filter by score, answered count, activity, or taxonomy."
        actions={
          <Badge variant="outline" className="h-7 rounded-full px-3 font-mono tracking-[0.08em]">
            {list.data ? `${total} learner${total === 1 ? "" : "s"}` : "learners"}
          </Badge>
        }
      />

      <section className="space-y-4">
        <div className="overflow-hidden rounded-xl border border-border bg-card">
          <div className="space-y-3 border-border border-b p-4">
            <div className="relative">
              <Search className="pointer-events-none absolute top-1/2 left-3 size-4 -translate-y-1/2 text-muted-foreground" />
              <Input
                value={searchInput}
                onChange={(event) => setSearchInput(event.target.value)}
                placeholder="Search name or email..."
                aria-label="Search students"
                maxLength={200}
                className="h-9 pl-9"
              />
            </div>

            <div className="flex flex-wrap items-center gap-2">
              <FilterSelect
                label="Score"
                value={scoreFilter}
                allValue="all"
                options={SCORE_OPTIONS}
                onChange={(value) => pickFilter(setScoreFilter, value)}
              />
              <FilterSelect
                label="Answered"
                value={answeredFilter}
                allValue="all"
                options={ANSWERED_OPTIONS}
                onChange={(value) => pickFilter(setAnsweredFilter, value)}
              />
              <FilterSelect
                label="Active"
                value={activityFilter}
                allValue="all"
                options={ACTIVITY_OPTIONS}
                onChange={(value) => pickFilter(setActivityFilter, value)}
              />
              <FilterSelect
                label="Taxonomy"
                value={curriculumFilter}
                allValue="all"
                options={taxonomyOptions}
                onChange={(value) => pickFilter(setCurriculumFilter, value)}
              />
              <Button variant="ghost" size="sm" disabled={!isFiltered} onClick={clearFilters}>
                Clear
              </Button>
            </div>
          </div>

          <div className="flex flex-wrap items-center gap-2 border-border border-b bg-muted/30 px-4 py-2.5">
            <FilterLabel>Active view</FilterLabel>
            {isFiltered ? (
              activeFilters.map((filter) => (
                <ActiveFilterChip
                  key={filter.label}
                  label={filter.label}
                  value={filter.value}
                  onClear={filter.onClear}
                />
              ))
            ) : (
              <span className="text-muted-foreground text-sm">No filters applied.</span>
            )}
          </div>

          <div>
            {list.isError ? <QueryError error={list.error} /> : null}
            {list.isPending ? <TableSkeleton /> : null}

            {list.isSuccess && total === 0 ? (
              <div className="p-5">
                {isFiltered ? (
                  <EmptyState
                    title="No students match this filter"
                    hint="Broaden the search or clear filters."
                  />
                ) : (
                  <EmptyState
                    title="No students yet"
                    hint="Students appear here after they join from a classroom link."
                  />
                )}
              </div>
            ) : null}

            {rows.length > 0 ? (
              <>
                <div
                  className={`transition-opacity ${list.isPlaceholderData ? "opacity-60" : ""}`}
                >
                  <Table className="table-auto">
                    <TableHeader className="[&_tr]:border-b-0">
                      <TableRow className="hover:bg-transparent">
                        <SortableHead label="Name" column="name" {...sortProps} />
                        <SortableHead label="Email" column="email" {...sortProps} />
                        <SortableHead label="Answered" column="answered" numeric {...sortProps} />
                        <SortableHead label="Avg score" column="average" numeric {...sortProps} />
                        <SortableHead label="Last active" column="last_active" {...sortProps} />
                        <SortableHead label="Enrolled" column="enrolled" {...sortProps} />
                      </TableRow>
                    </TableHeader>
                    <TableBody>
                      {rows.map((student) => (
                        <TableRow
                          key={student.id}
                          className="hover:!bg-accent/28 border-border/60 border-b odd:bg-background even:bg-muted/18"
                        >
                          <TableCell className="py-3 font-medium text-sm">
                            {student.display_name}
                          </TableCell>
                          <TableCell className="py-3 text-muted-foreground text-sm">
                            {student.email || "-"}
                          </TableCell>
                          <TableCell className="py-3 text-right font-mono text-sm tabular-nums">
                            {student.answered_count}
                          </TableCell>
                          <TableCell className="py-3 text-right font-mono text-sm tabular-nums">
                            {student.average_score == null
                              ? "-"
                              : student.average_score.toFixed(1)}
                          </TableCell>
                          <TableCell className="py-3">
                            <DateCell value={student.last_activity_at ?? null} />
                          </TableCell>
                          <TableCell className="py-3">
                            <DateCell value={student.created_at} />
                          </TableCell>
                        </TableRow>
                      ))}
                    </TableBody>
                  </Table>
                </div>

                <div className="flex flex-col gap-2 border-border/70 border-t bg-muted/18 px-5 py-4 text-muted-foreground text-sm md:flex-row md:items-center md:justify-between">
                  <p>
                    Page <span className="font-semibold text-foreground">{page}</span> of{" "}
                    <span className="font-semibold text-foreground">{pageCount}</span> ·{" "}
                    <span className="font-semibold text-foreground">{total}</span>{" "}
                    {isFiltered ? "matching " : ""}learner{total === 1 ? "" : "s"}
                  </p>
                  <div className="flex gap-2">
                    <Button
                      variant="outline"
                      size="sm"
                      disabled={page <= 1 || list.isPlaceholderData}
                      onClick={() => setPage((current) => Math.max(1, current - 1))}
                    >
                      Previous
                    </Button>
                    <Button
                      variant="outline"
                      size="sm"
                      disabled={page >= pageCount || list.isPlaceholderData}
                      onClick={() => setPage((current) => Math.min(pageCount, current + 1))}
                    >
                      Next
                    </Button>
                  </div>
                </div>
              </>
            ) : null}
          </div>
        </div>
      </section>
    </>
  );
}
