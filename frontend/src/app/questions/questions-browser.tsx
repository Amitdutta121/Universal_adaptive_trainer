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
  type SortingState,
  useReactTable,
} from "@tanstack/react-table";
import {
  ArrowUpDown,
  CheckCircle2,
  Database,
  Search,
  SlidersHorizontal,
  Sparkles,
  X,
} from "lucide-react";
import Link from "next/link";
import { parseAsInteger, parseAsString, parseAsStringLiteral, useQueryState } from "nuqs";
import { useDeferredValue, useMemo, useState } from "react";
import { PageHeader } from "@/components/page-header";
import { EmptyState, QueryError, TableSkeleton } from "@/components/query-state";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import {
  DropdownMenu,
  DropdownMenuCheckboxItem,
  DropdownMenuContent,
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
import { useCurriculumVersions, useQuestions } from "@/lib/api/queries";
import type {
  Difficulty,
  QuestionStatus,
  QuestionSummary,
  QuestionType,
  Schemas,
} from "@/lib/api/types";

type GeneratorKind = Schemas["GeneratorKind"];
type QuestionKind = Schemas["QuestionKind"];
type InstructionSource = NonNullable<QuestionSummary["instruction"]>["source"];

const STATUSES = [
  "generated",
  "validation_passed",
  "validation_failed",
  "approved",
  "rejected",
] as const satisfies readonly QuestionStatus[];

const DIFFICULTIES = ["easy", "medium", "hard"] as const satisfies readonly Difficulty[];
const QUESTION_TYPES = [
  "multiple_choice",
  "true_false",
  "output_prediction",
  "code_completion",
  "debugging",
  "parsons",
  "coding",
] as const satisfies readonly QuestionType[];
const QUESTION_KINDS = ["testable_program", "discrete"] as const satisfies readonly QuestionKind[];
const GENERATOR_KINDS = ["base", "personalized"] as const satisfies readonly GeneratorKind[];
const INSTRUCTION_SOURCES = ["learned", "shipped"] as const satisfies readonly InstructionSource[];
const VALIDATION_FILTERS = ["passed", "failed", "unknown"] as const;
const EDIT_FILTERS = ["edited", "unedited"] as const;
const LIMIT_OPTIONS = [25, 50, 100, 250] as const;
const DEFAULT_HIDDEN_COLUMNS: Record<string, boolean> = {
  kind: false,
  is_edited: false,
  priority: false,
  times_used: false,
  curriculum_version_id: true,
  topic_id: false,
  subtopic_ids: false,
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
      className="-ml-3 text-[0.72rem] font-medium uppercase tracking-[0.14em] text-muted-foreground hover:text-foreground"
      onClick={() => column.toggleSorting(column.getIsSorted() === "asc")}
    >
      {label} <ArrowUpDown className="size-3" />
    </Button>
  );
}

function formatDate(value: string | null) {
  if (!value) return "-";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return value;
  return new Intl.DateTimeFormat("en-US", {
    year: "numeric",
    month: "short",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
  }).format(date);
}

function textOrDash(value: string | number | null | undefined) {
  if (value === null || value === undefined || value === "") return "-";
  return String(value);
}

function FilterLabel({ children }: { children: string }) {
  return (
    <span className="font-mono text-[0.67rem] uppercase tracking-[0.16em] text-muted-foreground">
      {children}
    </span>
  );
}

function StatCard({
  label,
  value,
  hint,
  icon,
}: {
  label: string;
  value: string;
  hint: string;
  icon: React.ReactNode;
}) {
  return (
    <div className="rounded-2xl border border-border/70 bg-[linear-gradient(180deg,rgba(255,255,255,0.82),rgba(255,255,255,0.56))] p-4 shadow-[0_10px_30px_-24px_rgba(19,26,28,0.55)] backdrop-blur dark:bg-[linear-gradient(180deg,rgba(21,28,30,0.94),rgba(21,28,30,0.72))]">
      <div className="mb-3 flex items-center justify-between gap-3">
        <FilterLabel>{label}</FilterLabel>
        <span className="rounded-full border border-border/80 bg-background/70 p-2 text-muted-foreground">
          {icon}
        </span>
      </div>
      <div className="font-heading text-2xl leading-none tracking-[-0.03em] text-foreground">
        {value}
      </div>
      <p className="mt-2 text-sm text-muted-foreground">{hint}</p>
    </div>
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
      className="inline-flex items-center gap-2 rounded-full border border-border/80 bg-background/80 px-3 py-1.5 text-sm text-foreground shadow-[0_1px_0_rgba(255,255,255,0.45)_inset] transition-colors hover:bg-accent/70"
    >
      <span className="font-mono text-[0.66rem] uppercase tracking-[0.14em] text-muted-foreground">
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
      <Link
        href={`/questions/${row.original.id}`}
        className="font-mono text-xs font-semibold underline-offset-4 hover:text-primary hover:underline"
      >
        {row.original.id}
      </Link>
    ),
  },
  {
    accessorKey: "prompt",
    header: "Prompt",
    enableSorting: false,
    cell: ({ row }) => (
      <div className="min-w-72 max-w-lg whitespace-normal">
        <p className="line-clamp-3 text-sm leading-6 text-foreground">{row.original.prompt}</p>
      </div>
    ),
  },
  {
    accessorKey: "question_type",
    header: ({ column }) => <SortableHeader column={column} label="Type" />,
    cell: ({ row }) => (
      <span className="text-xs text-muted-foreground">
        {row.original.question_type?.replace(/_/g, " ") ?? "-"}
      </span>
    ),
  },
  {
    accessorKey: "kind",
    header: ({ column }) => <SortableHeader column={column} label="Kind" />,
    cell: ({ row }) => (
      <span className="text-xs text-muted-foreground">{row.original.kind.replace(/_/g, " ")}</span>
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
      <div className="max-w-48 whitespace-normal text-xs text-muted-foreground">
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
        <span className="text-xs text-muted-foreground">-</span>
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
    cell: ({ row }) => (
      <span className="text-xs text-muted-foreground">{formatDate(row.original.created_at)}</span>
    ),
  },
  {
    accessorKey: "updated_at",
    header: ({ column }) => <SortableHeader column={column} label="Updated" />,
    cell: ({ row }) => (
      <span className="text-xs text-muted-foreground">{formatDate(row.original.updated_at)}</span>
    ),
  },
];

export function QuestionsBrowser() {
  const [status, setStatus] = useQueryState("status", parseAsStringLiteral(STATUSES));
  const [limit, setLimit] = useQueryState("limit", parseAsInteger.withDefault(50));
  const [query, setQuery] = useQueryState("q", parseAsString.withDefault(""));
  const [difficulty, setDifficulty] = useQueryState(
    "difficulty",
    parseAsStringLiteral(DIFFICULTIES),
  );
  const [questionType, setQuestionType] = useQueryState(
    "question_type",
    parseAsStringLiteral(QUESTION_TYPES),
  );
  const [kind, setKind] = useQueryState("kind", parseAsStringLiteral(QUESTION_KINDS));
  const [generatorKind, setGeneratorKind] = useQueryState(
    "generator_kind",
    parseAsStringLiteral(GENERATOR_KINDS),
  );
  const [validation, setValidation] = useQueryState(
    "validation",
    parseAsStringLiteral(VALIDATION_FILTERS),
  );
  const [edited, setEdited] = useQueryState("edited", parseAsStringLiteral(EDIT_FILTERS));
  const [instructionSource, setInstructionSource] = useQueryState(
    "instruction_source",
    parseAsStringLiteral(INSTRUCTION_SOURCES),
  );
  const [taxonomyVersionId, setTaxonomyVersionId] = useQueryState("taxonomy", parseAsInteger);
  const [sorting, setSorting] = useState<SortingState>([{ id: "created_at", desc: true }]);
  const [columnVisibility, setColumnVisibility] =
    useState<Record<string, boolean>>(DEFAULT_HIDDEN_COLUMNS);

  const deferredQuery = useDeferredValue(query);
  const params = useMemo(
    () => ({
      limit,
      ...(status ? { status } : {}),
      ...(taxonomyVersionId !== null ? { curriculum_version_id: taxonomyVersionId } : {}),
    }),
    [limit, status, taxonomyVersionId],
  );
  const { data, isPending, isError, error } = useQuestions(params);
  const curriculumVersions = useCurriculumVersions();
  const taxonomyLabel = (versionId: number) =>
    curriculumVersions.data?.versions.find((version) => version.id === versionId)?.label ??
    `v${versionId}`;

  const filteredQuestions = useMemo(() => {
    const needle = deferredQuery.trim().toLowerCase();

    return (data?.questions ?? []).filter((question) => {
      if (difficulty && question.difficulty !== difficulty) return false;
      if (questionType && question.question_type !== questionType) return false;
      if (kind && question.kind !== kind) return false;
      if (generatorKind && question.generator_kind !== generatorKind) return false;
      if (instructionSource && question.instruction?.source !== instructionSource) return false;
      if (edited === "edited" && !question.is_edited) return false;
      if (edited === "unedited" && question.is_edited) return false;
      if (validation === "passed" && question.validation_passed !== true) return false;
      if (validation === "failed" && question.validation_passed !== false) return false;
      if (validation === "unknown" && question.validation_passed !== null) return false;
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
  }, [
    data?.questions,
    deferredQuery,
    difficulty,
    edited,
    generatorKind,
    instructionSource,
    kind,
    questionType,
    validation,
  ]);

  const approvedCount = filteredQuestions.filter(
    (question) => question.status === "approved",
  ).length;
  const editedCount = filteredQuestions.filter((question) => question.is_edited).length;
  const learnedCount = filteredQuestions.filter(
    (question) => question.instruction?.source === "learned",
  ).length;

  const activeFilters = [
    status
      ? { label: "status", value: status.replace(/_/g, " "), onClear: () => void setStatus(null) }
      : null,
    query ? { label: "search", value: query, onClear: () => void setQuery("") } : null,
    taxonomyVersionId !== null
      ? {
          label: "taxonomy",
          value: taxonomyLabel(taxonomyVersionId),
          onClear: () => void setTaxonomyVersionId(null),
        }
      : null,
    difficulty
      ? { label: "difficulty", value: difficulty, onClear: () => void setDifficulty(null) }
      : null,
    questionType
      ? {
          label: "type",
          value: questionType.replace(/_/g, " "),
          onClear: () => void setQuestionType(null),
        }
      : null,
    kind
      ? { label: "kind", value: kind.replace(/_/g, " "), onClear: () => void setKind(null) }
      : null,
    generatorKind
      ? {
          label: "generator",
          value: generatorKind,
          onClear: () => void setGeneratorKind(null),
        }
      : null,
    validation
      ? {
          label: "validation",
          value: validation,
          onClear: () => void setValidation(null),
        }
      : null,
    edited ? { label: "edited", value: edited, onClear: () => void setEdited(null) } : null,
    instructionSource
      ? {
          label: "instruction",
          value: instructionSource,
          onClear: () => void setInstructionSource(null),
        }
      : null,
    limit !== 50 ? { label: "rows", value: String(limit), onClear: () => void setLimit(50) } : null,
  ].filter((value): value is NonNullable<typeof value> => value !== null);

  const table = useReactTable({
    data: filteredQuestions,
    columns,
    state: { sorting, columnVisibility },
    onSortingChange: setSorting,
    onColumnVisibilityChange: setColumnVisibility,
    getCoreRowModel: getCoreRowModel(),
    getSortedRowModel: getSortedRowModel(),
  });

  const canClear = activeFilters.length > 0;

  return (
    <>
      <PageHeader
        title="Questions"
        summary="Generate, validate and review Python assessment questions."
        actions={
          <Badge variant="outline" className="h-7 rounded-full px-3 font-mono tracking-[0.08em]">
            live bank
          </Badge>
        }
      />

      <section className="space-y-4">
        <div className="grid gap-3 md:grid-cols-2 xl:grid-cols-4">
          <StatCard
            label="Loaded"
            value={String(data?.questions.length ?? 0)}
            hint={`${data?.total ?? 0} questions exist on the server`}
            icon={<Database className="size-4" />}
          />
          <StatCard
            label="Visible"
            value={String(filteredQuestions.length)}
            hint={activeFilters.length > 0 ? "Narrowed by active filters" : "Default live view"}
            icon={<Search className="size-4" />}
          />
          <StatCard
            label="Approved"
            value={String(approvedCount)}
            hint="Professor-approved rows in the current slice"
            icon={<CheckCircle2 className="size-4" />}
          />
          <StatCard
            label="Learned"
            value={String(learnedCount)}
            hint={`${editedCount} edited questions in this view`}
            icon={<Sparkles className="size-4" />}
          />
        </div>

        <div className="overflow-hidden rounded-[1.4rem] border border-border/70 bg-[linear-gradient(180deg,rgba(255,255,255,0.78),rgba(255,255,255,0.56))] shadow-[0_20px_45px_-32px_rgba(19,26,28,0.55)] backdrop-blur dark:bg-[linear-gradient(180deg,rgba(21,28,30,0.94),rgba(21,28,30,0.76))]">
          <div className="border-b border-border/70 bg-[radial-gradient(circle_at_top_left,rgba(46,111,106,0.14),transparent_38%),linear-gradient(180deg,rgba(255,255,255,0.6),transparent)] px-5 py-4 dark:bg-[radial-gradient(circle_at_top_left,rgba(102,184,176,0.16),transparent_42%),linear-gradient(180deg,rgba(255,255,255,0.03),transparent)]">
            <div className="flex flex-col gap-3 xl:flex-row xl:items-end xl:justify-between">
              <div className="space-y-2">
                <div className="flex items-center gap-2 text-muted-foreground">
                  <SlidersHorizontal className="size-4" />
                  <FilterLabel>Workbench</FilterLabel>
                </div>
                <div>
                  <p className="font-heading text-lg tracking-[-0.025em] text-foreground">
                    Scan faster, filter harder, keep context while scrolling.
                  </p>
                  <p className="max-w-3xl text-sm leading-6 text-muted-foreground">
                    Inspired by current data-table patterns that emphasize sticky headers, visible
                    filter state, and low-noise row scanning.
                  </p>
                </div>
              </div>

              <div className="flex flex-wrap items-center gap-2">
                <DropdownMenu>
                  <DropdownMenuTrigger asChild>
                    <Button
                      variant="outline"
                      size="sm"
                      className="border-border/80 bg-background/80"
                    >
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

                <Select
                  value={String(limit)}
                  onValueChange={(value) => void setLimit(Number(value))}
                >
                  <SelectTrigger
                    className="w-28 border-border/80 bg-background/80 shadow-[0_1px_0_rgba(255,255,255,0.48)_inset]"
                    size="sm"
                  >
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
          </div>

          <div className="grid gap-3 border-b border-border/70 bg-background/55 p-5 md:grid-cols-2 xl:grid-cols-5">
            <div className="space-y-2 md:col-span-2">
              <FilterLabel>Search</FilterLabel>
              <div className="relative">
                <Search className="pointer-events-none absolute top-1/2 left-3 size-4 -translate-y-1/2 text-muted-foreground" />
                <Input
                  value={query}
                  onChange={(event) => void setQuery(event.target.value)}
                  placeholder="Search prompt, ids, generator, fingerprint..."
                  className="h-10 border-border/80 bg-background/85 pl-9 shadow-[0_1px_0_rgba(255,255,255,0.45)_inset]"
                />
              </div>
            </div>

            <div className="space-y-2">
              <FilterLabel>Status</FilterLabel>
              <Select
                value={status ?? "all"}
                onValueChange={(value) =>
                  setStatus(value === "all" ? null : (value as QuestionStatus))
                }
              >
                <SelectTrigger
                  className="h-10 border-border/80 bg-background/85 shadow-[0_1px_0_rgba(255,255,255,0.45)_inset]"
                  size="sm"
                >
                  <SelectValue placeholder="All statuses" />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="all">All statuses</SelectItem>
                  {STATUSES.map((value) => (
                    <SelectItem key={value} value={value}>
                      {value.replace(/_/g, " ")}
                      {data ? ` (${data.status_counts[value] ?? 0})` : ""}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>

            <div className="space-y-2">
              <FilterLabel>Taxonomy</FilterLabel>
              <Select
                value={taxonomyVersionId !== null ? String(taxonomyVersionId) : "all"}
                onValueChange={(value) =>
                  void setTaxonomyVersionId(value === "all" ? null : Number(value))
                }
              >
                <SelectTrigger
                  className="h-10 border-border/80 bg-background/85 shadow-[0_1px_0_rgba(255,255,255,0.45)_inset]"
                  size="sm"
                >
                  <SelectValue placeholder="Any taxonomy" />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="all">Any taxonomy</SelectItem>
                  {(curriculumVersions.data?.versions ?? []).map((version) => (
                    <SelectItem key={version.id} value={String(version.id)}>
                      {version.label} (v{version.id})
                      {data ? ` — ${data.curriculum_version_counts[String(version.id)] ?? 0}` : ""}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>

            <div className="space-y-2">
              <FilterLabel>Difficulty</FilterLabel>
              <Select
                value={difficulty ?? "all"}
                onValueChange={(value) =>
                  setDifficulty(value === "all" ? null : (value as Difficulty))
                }
              >
                <SelectTrigger
                  className="h-10 border-border/80 bg-background/85 shadow-[0_1px_0_rgba(255,255,255,0.45)_inset]"
                  size="sm"
                >
                  <SelectValue placeholder="All difficulties" />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="all">All difficulties</SelectItem>
                  {DIFFICULTIES.map((value) => (
                    <SelectItem key={value} value={value}>
                      {value}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>

            <div className="space-y-2">
              <FilterLabel>Question Type</FilterLabel>
              <Select
                value={questionType ?? "all"}
                onValueChange={(value) =>
                  setQuestionType(value === "all" ? null : (value as QuestionType))
                }
              >
                <SelectTrigger
                  className="h-10 border-border/80 bg-background/85 shadow-[0_1px_0_rgba(255,255,255,0.45)_inset]"
                  size="sm"
                >
                  <SelectValue placeholder="All types" />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="all">All types</SelectItem>
                  {QUESTION_TYPES.map((value) => (
                    <SelectItem key={value} value={value}>
                      {value.replace(/_/g, " ")}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>

            <div className="space-y-2">
              <FilterLabel>Generator</FilterLabel>
              <Select
                value={generatorKind ?? "all"}
                onValueChange={(value) =>
                  setGeneratorKind(value === "all" ? null : (value as GeneratorKind))
                }
              >
                <SelectTrigger
                  className="h-10 border-border/80 bg-background/85 shadow-[0_1px_0_rgba(255,255,255,0.45)_inset]"
                  size="sm"
                >
                  <SelectValue placeholder="All generators" />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="all">All generators</SelectItem>
                  {GENERATOR_KINDS.map((value) => (
                    <SelectItem key={value} value={value}>
                      {value}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>

            <div className="space-y-2">
              <FilterLabel>Kind</FilterLabel>
              <Select
                value={kind ?? "all"}
                onValueChange={(value) => setKind(value === "all" ? null : (value as QuestionKind))}
              >
                <SelectTrigger
                  className="h-10 border-border/80 bg-background/85 shadow-[0_1px_0_rgba(255,255,255,0.45)_inset]"
                  size="sm"
                >
                  <SelectValue placeholder="All kinds" />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="all">All kinds</SelectItem>
                  {QUESTION_KINDS.map((value) => (
                    <SelectItem key={value} value={value}>
                      {value.replace(/_/g, " ")}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>

            <div className="space-y-2">
              <FilterLabel>Validation</FilterLabel>
              <Select
                value={validation ?? "all"}
                onValueChange={(value) =>
                  setValidation(
                    value === "all" ? null : (value as (typeof VALIDATION_FILTERS)[number]),
                  )
                }
              >
                <SelectTrigger
                  className="h-10 border-border/80 bg-background/85 shadow-[0_1px_0_rgba(255,255,255,0.45)_inset]"
                  size="sm"
                >
                  <SelectValue placeholder="Any validation" />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="all">Any validation</SelectItem>
                  {VALIDATION_FILTERS.map((value) => (
                    <SelectItem key={value} value={value}>
                      {value}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>

            <div className="space-y-2">
              <FilterLabel>Edit State</FilterLabel>
              <Select
                value={edited ?? "all"}
                onValueChange={(value) =>
                  setEdited(value === "all" ? null : (value as (typeof EDIT_FILTERS)[number]))
                }
              >
                <SelectTrigger
                  className="h-10 border-border/80 bg-background/85 shadow-[0_1px_0_rgba(255,255,255,0.45)_inset]"
                  size="sm"
                >
                  <SelectValue placeholder="Edited or original" />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="all">Edited or original</SelectItem>
                  {EDIT_FILTERS.map((value) => (
                    <SelectItem key={value} value={value}>
                      {value}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>

            <div className="space-y-2">
              <FilterLabel>Instruction</FilterLabel>
              <Select
                value={instructionSource ?? "all"}
                onValueChange={(value) =>
                  setInstructionSource(value === "all" ? null : (value as InstructionSource))
                }
              >
                <SelectTrigger
                  className="h-10 border-border/80 bg-background/85 shadow-[0_1px_0_rgba(255,255,255,0.45)_inset]"
                  size="sm"
                >
                  <SelectValue placeholder="Any instruction" />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="all">Any instruction</SelectItem>
                  {INSTRUCTION_SOURCES.map((value) => (
                    <SelectItem key={value} value={value}>
                      {value}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>

            <div className="flex items-end">
              <Button
                variant="outline"
                size="sm"
                className="h-10 w-full border-border/80 bg-background/85"
                disabled={!canClear}
                onClick={() => {
                  void setStatus(null);
                  void setLimit(50);
                  void setQuery("");
                  void setTaxonomyVersionId(null);
                  void setDifficulty(null);
                  void setQuestionType(null);
                  void setKind(null);
                  void setGeneratorKind(null);
                  void setValidation(null);
                  void setEdited(null);
                  void setInstructionSource(null);
                }}
              >
                Clear filters
              </Button>
            </div>
          </div>

          <div className="flex flex-wrap items-center gap-2 border-b border-border/70 bg-muted/20 px-5 py-3">
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
              <span className="text-sm text-muted-foreground">
                No filters applied. You are looking at the default view.
              </span>
            )}
          </div>

          <div className="rounded-b-[1.4rem] bg-background/70">
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
                <div className="max-h-[68vh] overflow-auto">
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
                                  "sticky top-0 z-10 border-b border-border/80 bg-[color-mix(in_oklch,var(--background),white_55%)] py-3 text-[0.72rem] uppercase tracking-[0.14em] text-muted-foreground backdrop-blur",
                                  numeric ? "text-right" : "",
                                  stickyLeft ? "left-0 z-20 shadow-[1px_0_0_var(--border)]" : "",
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
                          className="border-b border-border/60 odd:bg-background even:bg-muted/18 hover:!bg-accent/28"
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
                                  numeric ? "font-mono tabular-nums text-right" : "",
                                  stickyLeft
                                    ? "sticky left-0 z-10 border-r border-border/70 bg-inherit shadow-[1px_0_0_var(--border)]"
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

                <div className="flex flex-col gap-2 border-t border-border/70 bg-muted/18 px-5 py-4 text-sm text-muted-foreground md:flex-row md:items-center md:justify-between">
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
                  <p className="font-mono text-[0.72rem] uppercase tracking-[0.14em]">
                    Sticky header + active filter state
                  </p>
                </div>
              </>
            ) : null}
          </div>
        </div>
      </section>
    </>
  );
}
