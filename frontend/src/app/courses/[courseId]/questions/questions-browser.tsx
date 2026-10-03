"use client";

/**
 * The question bank.
 *
 * This is the worked example of the interactive pattern: filters live in the URL so
 * a professor can share or reload a filtered view, server state lives in TanStack
 * Query, and the row model comes from TanStack Table. Every field below is typed
 * from the backend's OpenAPI document so a schema rename breaks at compile time.
 */

import {
  type ColumnDef,
  flexRender,
  getCoreRowModel,
  getSortedRowModel,
  type RowData,
  type SortingState,
  useReactTable,
} from "@tanstack/react-table";
import { ArrowUpDown, ChevronDown, Layers, Search, Wand2, X } from "lucide-react";
import {
  parseAsArrayOf,
  parseAsInteger,
  parseAsString,
  parseAsStringLiteral,
  useQueryState,
} from "nuqs";
import { useDeferredValue, useMemo, useState } from "react";
import { QuestionReview } from "@/app/courses/[courseId]/questions/generate/single/components/question-review";
import { PageHeader } from "@/components/page-header";
import { EmptyState, QueryError, TableSkeleton } from "@/components/query-state";
import { StartCard } from "@/components/start-card";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import {
  DropdownMenu,
  DropdownMenuCheckboxItem,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuLabel,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import { Input } from "@/components/ui/input";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import {
  useApprovedCurriculum,
  useAssessmentCatalog,
  useCourse,
  useQuestions,
} from "@/lib/api/queries";
import type { Difficulty, QuestionStatus, QuestionSummary } from "@/lib/api/types";
import { CourseLink } from "@/components/course-link";
import { BUILT_QUESTION_TYPES, questionTypeLabel } from "@/lib/question-types/registry";
import { useCourseId } from "@/lib/use-course";
import { questionsSummary, subjectLabel } from "./questions-summary";

// The row click-through is handed to the columns through TanStack's `meta`, so the
// column defs can stay module-level constants instead of closing over component state.
declare module "@tanstack/react-table" {
  interface TableMeta<TData extends RowData> {
    openPreview: (id: number) => void;
  }
}

const STATUSES = [
  "generated",
  "validation_passed",
  "validation_failed",
  "approved",
  "rejected",
] as const satisfies readonly QuestionStatus[];

const DIFFICULTIES = ["easy", "medium", "hard"] as const satisfies readonly Difficulty[];
const QUESTION_TYPES = BUILT_QUESTION_TYPES;
const LIMIT_OPTIONS = [25, 50, 100, 250] as const;
// The defaults fit the page width, so the page is the only scroller; anything wider is
// opt-in from the Columns menu. Curriculum is off because every row is the header's taxonomy.
const DEFAULT_HIDDEN_COLUMNS: Record<string, boolean> = {
  kind: false,
  is_edited: false,
  priority: false,
  times_used: false,
  curriculum_version_id: false,
  topic_id: false,
  subtopic_ids: false,
  generator_kind: false,
  generator_name: false,
  generator_version: false,
  generator_label: false,
  instruction_source: false,
  instruction_fingerprint: false,
  instruction_rule_count: false,
  instruction_review_count: false,
  updated_at: false,
};
const NUMERIC_COLUMNS = new Set([
  "priority",
  "times_used",
  "curriculum_version_id",
  "topic_id",
  "instruction_rule_count",
  "instruction_review_count",
]);

const STATUS_VARIANT: Record<QuestionStatus, "default" | "secondary" | "destructive" | "outline"> =
  {
    approved: "default",
    validation_passed: "secondary",
    generated: "outline",
    validation_failed: "destructive",
    rejected: "destructive",
  };

const DIFFICULTY_VARIANT: Record<Difficulty, "outline" | "secondary" | "default"> = {
  easy: "outline",
  medium: "secondary",
  hard: "default",
};

function SortableHeader({
  column,
  label,
}: {
  column: { getIsSorted: () => false | "asc" | "desc"; toggleSorting: (desc?: boolean) => void };
  label: string;
}) {
  return (
    <Button
      variant="ghost"
      size="sm"
      className="-ml-3 font-medium text-[0.72rem] text-muted-foreground uppercase tracking-[0.14em] hover:text-foreground"
      onClick={() => column.toggleSorting(column.getIsSorted() === "asc")}
    >
      {label} <ArrowUpDown className="size-3" />
    </Button>
  );
}

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

/** The date in the cell, the full timestamp on hover: keeps the column narrow. */
function DateCell({ value }: { value: string | null }) {
  return (
    <span className="whitespace-nowrap text-muted-foreground text-xs" title={formatDate(value)}>
      {formatDate(value, false)}
    </span>
  );
}

function textOrDash(value: string | number | null | undefined) {
  if (value === null || value === undefined || value === "") return "-";
  return String(value);
}

function FilterLabel({ children }: { children: string }) {
  return (
    <span className="font-mono text-[0.67rem] text-muted-foreground uppercase tracking-[0.16em]">
      {children}
    </span>
  );
}

/**
 * One filter as a button that names the filter and what it keeps ("Status: Approved +1"),
 * opening a checklist so several values can be kept at once. The menu stays open while
 * ticking; no values ticked means the filter is off.
 */
function FilterMultiSelect<T extends string>({
  label,
  allLabel,
  value,
  options,
  onChange,
}: {
  label: string;
  allLabel: string;
  value: readonly T[];
  options: readonly { value: T; label: string; count?: number }[];
  onChange: (value: T[]) => void;
}) {
  const chosen = options.filter((option) => value.includes(option.value));
  const toggle = (option: T, on: boolean) =>
    // Kept in the options' order so the URL and the button read the same every time.
    onChange(
      options
        .map((each) => each.value)
        .filter((each) => (each === option ? on : value.includes(each))),
    );
  return (
    <DropdownMenu>
      <DropdownMenuTrigger asChild>
        <Button variant="outline" className="h-9 min-w-40 justify-between font-normal">
          <span>
            <span className="text-muted-foreground">{label}:</span>{" "}
            {chosen.length === 0 ? (
              allLabel
            ) : (
              <span className="capitalize">
                {chosen[0].label}
                {chosen.length > 1 ? (
                  <span className="text-muted-foreground"> +{chosen.length - 1}</span>
                ) : null}
              </span>
            )}
          </span>
          <ChevronDown className="size-4 text-muted-foreground" />
        </Button>
      </DropdownMenuTrigger>
      <DropdownMenuContent align="start" className="min-w-56">
        {options.map((option) => (
          <DropdownMenuCheckboxItem
            key={option.value}
            checked={value.includes(option.value)}
            onCheckedChange={(on) => toggle(option.value, on)}
            onSelect={(event) => event.preventDefault()}
            className="capitalize"
          >
            {option.label}
            {option.count !== undefined ? (
              <span className="ml-auto pl-3 text-muted-foreground tabular-nums">
                {option.count}
              </span>
            ) : null}
          </DropdownMenuCheckboxItem>
        ))}
        {value.length > 0 ? (
          <>
            <DropdownMenuSeparator />
            <DropdownMenuItem onSelect={() => onChange([])}>
              Clear {label.toLowerCase()}
            </DropdownMenuItem>
          </>
        ) : null}
      </DropdownMenuContent>
    </DropdownMenu>
  );
}

function ActiveFilterChip({
  label,
  value,
  onClear,
}: {
  label: string;
  value: string;
  onClear: () => void;
}) {
  return (
    <button
      type="button"
      onClick={onClear}
      className="inline-flex items-center gap-2 rounded-full border border-border/80 bg-background/80 px-3 py-1.5 text-foreground text-sm shadow-[0_1px_0_rgba(255,255,255,0.45)_inset] transition-colors hover:bg-accent/70"
    >
      <span className="font-mono text-[0.66rem] text-muted-foreground uppercase tracking-[0.14em]">
        {label}
      </span>
      <span>{value}</span>
      <X className="size-3.5 text-muted-foreground" />
    </button>
  );
}

const columns: ColumnDef<QuestionSummary>[] = [
  {
    accessorKey: "id",
    header: ({ column }) => <SortableHeader column={column} label="ID" />,
    cell: ({ row }) => (
      <CourseLink
        href={`/questions/${row.original.id}`}
        className="font-mono font-semibold text-xs underline-offset-4 hover:text-primary hover:underline"
      >
        {row.original.id}
      </CourseLink>
    ),
  },
  {
    accessorKey: "prompt",
    header: "Prompt",
    enableSorting: false,
    cell: ({ row, table }) => (
      <button
        type="button"
        onClick={() => table.options.meta?.openPreview(row.original.id)}
        className="block min-w-48 max-w-lg whitespace-normal text-left"
      >
        <p className="line-clamp-3 text-foreground text-sm leading-6 underline-offset-4 hover:underline">
          {row.original.prompt}
        </p>
      </button>
    ),
  },
  {
    accessorKey: "question_type",
    header: ({ column }) => <SortableHeader column={column} label="Type" />,
    cell: ({ row }) => (
      <span className="text-muted-foreground text-xs">
        {row.original.question_type?.replace(/_/g, " ") ?? "-"}
      </span>
    ),
  },
  {
    accessorKey: "kind",
    header: ({ column }) => <SortableHeader column={column} label="Kind" />,
    cell: ({ row }) => (
      <span className="text-muted-foreground text-xs">{row.original.kind.replace(/_/g, " ")}</span>
    ),
  },
  {
    accessorKey: "difficulty",
    header: ({ column }) => <SortableHeader column={column} label="Difficulty" />,
    cell: ({ row }) => (
      <Badge variant={DIFFICULTY_VARIANT[row.original.difficulty]}>{row.original.difficulty}</Badge>
    ),
  },
  {
    accessorKey: "status",
    header: ({ column }) => <SortableHeader column={column} label="Status" />,
    cell: ({ row }) => (
      <Badge variant={STATUS_VARIANT[row.original.status]}>
        {row.original.status.replace(/_/g, " ")}
      </Badge>
    ),
  },
  {
    accessorKey: "validation_passed",
    header: ({ column }) => <SortableHeader column={column} label="Validation" />,
    cell: ({ row }) => {
      const value = row.original.validation_passed;
      if (value === null) return <Badge variant="outline">unknown</Badge>;
      return (
        <Badge variant={value ? "secondary" : "destructive"}>{value ? "passed" : "failed"}</Badge>
      );
    },
  },
  {
    accessorKey: "is_edited",
    header: ({ column }) => <SortableHeader column={column} label="Edited" />,
    cell: ({ row }) => (
      <Badge variant={row.original.is_edited ? "default" : "outline"}>
        {row.original.is_edited ? "edited" : "original"}
      </Badge>
    ),
  },
  {
    accessorKey: "priority",
    header: ({ column }) => <SortableHeader column={column} label="Priority" />,
  },
  {
    accessorKey: "times_used",
    header: ({ column }) => <SortableHeader column={column} label="Usage" />,
  },
  {
    accessorKey: "curriculum_version_id",
    header: ({ column }) => <SortableHeader column={column} label="Curriculum" />,
    cell: ({ row }) => textOrDash(row.original.curriculum_version_id),
  },
  {
    accessorKey: "topic_id",
    header: ({ column }) => <SortableHeader column={column} label="Topic" />,
    cell: ({ row }) => textOrDash(row.original.topic_id),
  },
  {
    accessorKey: "subtopic_ids",
    header: "Subtopics",
    enableSorting: false,
    cell: ({ row }) => (
      <div className="max-w-48 whitespace-normal text-muted-foreground text-xs">
        {row.original.subtopic_ids.length > 0 ? row.original.subtopic_ids.join(", ") : "-"}
      </div>
    ),
  },
  {
    accessorKey: "generator_kind",
    header: ({ column }) => <SortableHeader column={column} label="Generator" />,
    cell: ({ row }) => <Badge variant="outline">{row.original.generator_kind}</Badge>,
  },
  {
    accessorKey: "generator_name",
    header: ({ column }) => <SortableHeader column={column} label="Generator name" />,
    cell: ({ row }) => (
      <div className="max-w-40 whitespace-normal text-xs">{row.original.generator_name}</div>
    ),
  },
  {
    accessorKey: "generator_version",
    header: ({ column }) => <SortableHeader column={column} label="Version" />,
    cell: ({ row }) => <span className="font-mono text-xs">{row.original.generator_version}</span>,
  },
  {
    accessorKey: "generator_label",
    header: ({ column }) => <SortableHeader column={column} label="Label" />,
    cell: ({ row }) => <span className="font-mono text-xs">{row.original.generator_label}</span>,
  },
  {
    id: "instruction_source",
    accessorFn: (row) => row.instruction?.source ?? null,
    header: ({ column }) => <SortableHeader column={column} label="Instruction" />,
    cell: ({ row }) =>
      row.original.instruction ? (
        <Badge variant={row.original.instruction.source === "learned" ? "secondary" : "outline"}>
          {row.original.instruction.source}
        </Badge>
      ) : (
        <span className="text-muted-foreground text-xs">-</span>
      ),
  },
  {
    id: "instruction_fingerprint",
    accessorFn: (row) => row.instruction?.fingerprint ?? null,
    header: ({ column }) => <SortableHeader column={column} label="Fingerprint" />,
    cell: ({ row }) => (
      <span className="font-mono text-xs">
        {row.original.instruction?.fingerprint.slice(0, 12) ?? "-"}
      </span>
    ),
  },
  {
    id: "instruction_rule_count",
    accessorFn: (row) => row.instruction?.rule_count ?? null,
    header: ({ column }) => <SortableHeader column={column} label="Rules" />,
    cell: ({ row }) => textOrDash(row.original.instruction?.rule_count),
  },
  {
    id: "instruction_review_count",
    accessorFn: (row) => row.instruction?.review_count ?? null,
    header: ({ column }) => <SortableHeader column={column} label="Reviews" />,
    cell: ({ row }) => textOrDash(row.original.instruction?.review_count),
  },
  {
    accessorKey: "created_at",
    header: ({ column }) => <SortableHeader column={column} label="Created" />,
    cell: ({ row }) => <DateCell value={row.original.created_at} />,
  },
  {
    accessorKey: "updated_at",
    header: ({ column }) => <SortableHeader column={column} label="Updated" />,
    cell: ({ row }) => <DateCell value={row.original.updated_at} />,
  },
];

export function QuestionsBrowser() {
  const course = useCourse(useCourseId());
  const catalog = useAssessmentCatalog();
  const summary = questionsSummary(subjectLabel(course.data?.subject, catalog.data?.subjects));
  // Each multi-select keeps "any of these" in the URL as a comma list; empty means off.
  const [status, setStatus] = useQueryState(
    "status",
    parseAsArrayOf(parseAsStringLiteral(STATUSES)).withDefault([]),
  );
  const [limit, setLimit] = useQueryState("limit", parseAsInteger.withDefault(50));
  const [query, setQuery] = useQueryState("q", parseAsString.withDefault(""));
  const [difficulty, setDifficulty] = useQueryState(
    "difficulty",
    parseAsArrayOf(parseAsStringLiteral(DIFFICULTIES)).withDefault([]),
  );
  const [questionType, setQuestionType] = useQueryState(
    "question_type",
    parseAsArrayOf(parseAsStringLiteral(QUESTION_TYPES)).withDefault([]),
  );
  const [runId, setRunId] = useQueryState("run_id", parseAsString);
  const [previewId, setPreviewId] = useQueryState("preview", parseAsInteger);
  const [sorting, setSorting] = useState<SortingState>([{ id: "created_at", desc: true }]);
  const [columnVisibility, setColumnVisibility] =
    useState<Record<string, boolean>>(DEFAULT_HIDDEN_COLUMNS);

  // The bank shows the taxonomy chosen in the header, like every other page.
  const selectedTaxonomy = useApprovedCurriculum();
  const selectedTaxonomyId = selectedTaxonomy.data?.version.id ?? null;

  const deferredQuery = useDeferredValue(query);
  const params = useMemo(
    () => ({
      limit,
      ...(status.length > 0 ? { status } : {}),
      ...(selectedTaxonomyId !== null ? { curriculum_version_id: selectedTaxonomyId } : {}),
      ...(runId ? { run_id: runId } : {}),
    }),
    [limit, status, selectedTaxonomyId, runId],
  );
  const { data, isPending, isError, error } = useQuestions(params);

  const filteredQuestions = useMemo(() => {
    const needle = deferredQuery.trim().toLowerCase();

    return (data?.questions ?? []).filter((question) => {
      if (difficulty.length > 0 && !difficulty.includes(question.difficulty)) return false;
      if (
        questionType.length > 0 &&
        (question.question_type === null || !questionType.includes(question.question_type))
      )
        return false;
      if (!needle) return true;

      const searchable = [
        question.id,
        question.prompt,
        question.question_type,
        question.kind,
        question.difficulty,
        question.status,
        question.curriculum_version_id,
        question.topic_id,
        question.subtopic_ids.join(" "),
        question.generator_kind,
        question.generator_name,
        question.generator_version,
        question.generator_label,
        question.instruction?.source,
        question.instruction?.fingerprint,
        question.priority,
        question.times_used,
        question.created_at,
        question.updated_at,
      ]
        .filter((value) => value !== null && value !== undefined)
        .join(" ")
        .toLowerCase();

      return searchable.includes(needle);
    });
  }, [data?.questions, deferredQuery, difficulty, questionType]);

  const activeFilters = [
    status.length > 0
      ? {
          label: "status",
          value: status.map((value) => value.replace(/_/g, " ")).join(", "),
          onClear: () => void setStatus(null),
        }
      : null,
    query ? { label: "search", value: query, onClear: () => void setQuery("") } : null,
    difficulty.length > 0
      ? {
          label: "difficulty",
          value: difficulty.join(", "),
          onClear: () => void setDifficulty(null),
        }
      : null,
    questionType.length > 0
      ? {
          label: "type",
          value: questionType.map(questionTypeLabel).join(", "),
          onClear: () => void setQuestionType(null),
        }
      : null,
    runId ? { label: "run", value: runId, onClear: () => void setRunId(null) } : null,
  ].filter((value): value is NonNullable<typeof value> => value !== null);

  const table = useReactTable({
    data: filteredQuestions,
    columns,
    state: { sorting, columnVisibility },
    onSortingChange: setSorting,
    onColumnVisibilityChange: setColumnVisibility,
    getCoreRowModel: getCoreRowModel(),
    getSortedRowModel: getSortedRowModel(),
    meta: { openPreview: (id) => void setPreviewId(id) },
  });

  const previewRow =
    previewId !== null
      ? (filteredQuestions.find((question) => question.id === previewId) ?? null)
      : null;

  const canClear = activeFilters.length > 0;

  return (
    <>
      <PageHeader
        title="Questions"
        summary={summary}
        actions={
          <div className="flex items-center gap-2">
            <Button asChild variant="outline" size="sm" className="h-9 border-border/80">
              <CourseLink href="/coverage">Show coverage</CourseLink>
            </Button>
            <Badge variant="outline" className="h-7 rounded-full px-3 font-mono tracking-[0.08em]">
              live bank
            </Badge>
          </div>
        }
      />

      <section className="space-y-4">
        {/* The two ways questions are made. Each opens its own generate screen. */}
        <div className="grid gap-4 md:grid-cols-2">
          <StartCard
            icon={<Wand2 className="size-4" />}
            title="Generate questions"
            description="Pick a chunk of a book and generate questions from it one at a time, reviewing each as it arrives."
            action="Generate questions"
            href="/questions/generate/single"
          />
          <StartCard
            icon={<Layers className="size-4" />}
            title="Bulk generate"
            description="Plan a whole sheet across the approved taxonomy and generate every row in one run."
            action="Bulk generate"
            href="/questions/generate"
          />
        </div>

        <div className="overflow-hidden rounded-xl border border-border bg-card">
          <div className="space-y-3 border-border border-b p-4">
            <div className="relative">
              <Search className="pointer-events-none absolute top-1/2 left-3 size-4 -translate-y-1/2 text-muted-foreground" />
              <Input
                value={query}
                onChange={(event) => void setQuery(event.target.value)}
                placeholder="Search prompt, ids, generator, fingerprint..."
                aria-label="Search questions"
                className="h-9 pl-9"
              />
            </div>

            <div className="flex flex-wrap items-center gap-2">
              <FilterMultiSelect
                label="Status"
                allLabel="All"
                value={status}
                options={STATUSES.map((value) => ({
                  value,
                  label: value.replace(/_/g, " "),
                  count: data?.status_counts[value],
                }))}
                onChange={(value) => void setStatus(value.length > 0 ? value : null)}
              />
              <FilterMultiSelect
                label="Difficulty"
                allLabel="All"
                value={difficulty}
                options={DIFFICULTIES.map((value) => ({ value, label: value }))}
                onChange={(value) => void setDifficulty(value.length > 0 ? value : null)}
              />
              <FilterMultiSelect
                label="Type"
                allLabel="All types"
                value={questionType}
                options={QUESTION_TYPES.map((value) => ({
                  value,
                  label: questionTypeLabel(value),
                }))}
                onChange={(value) => void setQuestionType(value.length > 0 ? value : null)}
              />
              <Button
                variant="ghost"
                size="sm"
                disabled={!canClear}
                onClick={() => {
                  void setStatus(null);
                  void setQuery("");
                  void setDifficulty(null);
                  void setQuestionType(null);
                  void setRunId(null);
                }}
              >
                Clear
              </Button>
            </div>
          </div>

          <div className="flex flex-wrap items-center gap-2 border-border border-b bg-muted/30 px-4 py-2.5">
            <FilterLabel>Active view</FilterLabel>
            {activeFilters.length > 0 ? (
              activeFilters.map((filter) => (
                <ActiveFilterChip
                  key={`${filter.label}-${filter.value}`}
                  label={filter.label}
                  value={filter.value}
                  onClear={filter.onClear}
                />
              ))
            ) : (
              <span className="text-muted-foreground text-sm">No filters applied.</span>
            )}

            <div className="ml-auto flex items-center gap-2">
              <DropdownMenu>
                <DropdownMenuTrigger asChild>
                  <Button variant="outline" size="sm">
                    Columns
                  </Button>
                </DropdownMenuTrigger>
                <DropdownMenuContent align="end" className="w-56">
                  <DropdownMenuLabel>Visible columns</DropdownMenuLabel>
                  <DropdownMenuSeparator />
                  {table
                    .getAllColumns()
                    .filter((column) => column.getCanHide())
                    .map((column) => (
                      <DropdownMenuCheckboxItem
                        key={column.id}
                        checked={column.getIsVisible()}
                        onCheckedChange={(value) => column.toggleVisibility(!!value)}
                      >
                        {column.id.replace(/_/g, " ")}
                      </DropdownMenuCheckboxItem>
                    ))}
                </DropdownMenuContent>
              </DropdownMenu>

              <Select value={String(limit)} onValueChange={(value) => void setLimit(Number(value))}>
                <SelectTrigger className="w-28" size="sm" aria-label="Rows to load">
                  <SelectValue placeholder="Rows" />
                </SelectTrigger>
                <SelectContent>
                  {LIMIT_OPTIONS.map((value) => (
                    <SelectItem key={value} value={String(value)}>
                      {value} rows
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>
          </div>

          <div>
            {isError ? <QueryError error={error} /> : null}
            {isPending ? <TableSkeleton /> : null}

            {data && filteredQuestions.length === 0 ? (
              <div className="p-5">
                <EmptyState
                  title="No questions match this filter"
                  hint="Broaden the search, clear filters, or load more rows from the server."
                />
              </div>
            ) : null}

            {data && filteredQuestions.length > 0 ? (
              <>
                <div>
                  <Table className="table-auto">
                    <TableHeader className="[&_tr]:border-b-0">
                      {table.getHeaderGroups().map((headerGroup) => (
                        <TableRow key={headerGroup.id} className="hover:bg-transparent">
                          {headerGroup.headers.map((header) => {
                            const stickyLeft = header.column.id === "id";
                            const numeric = NUMERIC_COLUMNS.has(header.column.id);
                            return (
                              <TableHead
                                key={header.id}
                                className={[
                                  "border-border/80 border-b bg-muted/30 py-3 text-[0.72rem] text-muted-foreground uppercase tracking-[0.14em]",
                                  numeric ? "text-right" : "",
                                  stickyLeft
                                    ? "sticky left-0 z-20 shadow-[1px_0_0_var(--border)]"
                                    : "",
                                ].join(" ")}
                              >
                                {header.isPlaceholder
                                  ? null
                                  : flexRender(header.column.columnDef.header, header.getContext())}
                              </TableHead>
                            );
                          })}
                        </TableRow>
                      ))}
                    </TableHeader>
                    <TableBody>
                      {table.getRowModel().rows.map((row) => (
                        <TableRow
                          key={row.id}
                          className="hover:!bg-accent/28 border-border/60 border-b odd:bg-background even:bg-muted/18"
                        >
                          {row.getVisibleCells().map((cell) => {
                            const stickyLeft = cell.column.id === "id";
                            const compact = cell.column.id !== "prompt";
                            const numeric = NUMERIC_COLUMNS.has(cell.column.id);
                            return (
                              <TableCell
                                key={cell.id}
                                className={[
                                  "align-top",
                                  compact ? "py-3 text-sm" : "py-4",
                                  numeric ? "text-right font-mono tabular-nums" : "",
                                  stickyLeft
                                    ? "sticky left-0 z-10 border-border/70 border-r bg-inherit shadow-[1px_0_0_var(--border)]"
                                    : "",
                                ].join(" ")}
                              >
                                {flexRender(cell.column.columnDef.cell, cell.getContext())}
                              </TableCell>
                            );
                          })}
                        </TableRow>
                      ))}
                    </TableBody>
                  </Table>
                </div>

                <div className="flex flex-col gap-2 border-border/70 border-t bg-muted/18 px-5 py-4 text-muted-foreground text-sm md:flex-row md:items-center md:justify-between">
                  <p>
                    Showing{" "}
                    <span className="font-semibold text-foreground">
                      {filteredQuestions.length}
                    </span>{" "}
                    filtered rows from{" "}
                    <span className="font-semibold text-foreground">{data.questions.length}</span>{" "}
                    loaded and <span className="font-semibold text-foreground">{data.total}</span>{" "}
                    total on the server.
                  </p>
                </div>
              </>
            ) : null}
          </div>
        </div>
      </section>

      <Dialog
        open={previewId !== null}
        onOpenChange={(open) => {
          if (!open) void setPreviewId(null);
        }}
      >
        <DialogContent className="max-h-[85vh] overflow-y-auto sm:max-w-3xl">
          <DialogHeader>
            <DialogTitle>{previewId !== null ? `Question ${previewId}` : "Question"}</DialogTitle>
            <DialogDescription>
              {previewRow
                ? `${previewRow.question_type?.replace(/_/g, " ") ?? "unclassified"} — ${previewRow.difficulty}`
                : "Preview, review, edit, or reject this question."}
            </DialogDescription>
          </DialogHeader>
          {previewId !== null ? (
            <QuestionReview
              key={previewId}
              questionId={previewId}
              onRegenerated={(id) => void setPreviewId(id)}
            />
          ) : null}
        </DialogContent>
      </Dialog>
    </>
  );
}
