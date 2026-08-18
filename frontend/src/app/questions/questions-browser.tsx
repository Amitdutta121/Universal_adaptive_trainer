"use client";

/**
 * The question bank.
 *
 * This is the worked example of the interactive pattern: filters live in the URL so
 * a professor can share or reload a filtered view, server state lives in TanStack
 * Query, and the row model comes from TanStack Table. Every field below is typed
 * from the backend's OpenAPI document — `question.difficulty` cannot be misspelled.
 */

import {
  type ColumnDef,
  flexRender,
  getCoreRowModel,
  getSortedRowModel,
  type SortingState,
  useReactTable,
} from "@tanstack/react-table";
import { ArrowUpDown } from "lucide-react";
import Link from "next/link";
import { parseAsInteger, parseAsStringLiteral, useQueryState } from "nuqs";
import { useMemo, useState } from "react";
import { PageHeader } from "@/components/page-header";
import { EmptyState, QueryError, TableSkeleton } from "@/components/query-state";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
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
import { useQuestions } from "@/lib/api/queries";
import type { Difficulty, QuestionStatus, QuestionSummary } from "@/lib/api/types";

/** Mirrors the backend `QuestionStatus` enum; a value the API rejects cannot be selected. */
const STATUSES = [
  "generated",
  "validation_passed",
  "validation_failed",
  "approved",
  "rejected",
] as const satisfies readonly QuestionStatus[];

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

const columns: ColumnDef<QuestionSummary>[] = [
  {
    accessorKey: "id",
    header: "#",
    cell: ({ row }) => (
      <Link
        href={`/questions/${row.original.id}`}
        className="font-mono text-xs underline-offset-4 hover:underline"
      >
        {row.original.id}
      </Link>
    ),
  },
  {
    accessorKey: "prompt",
    header: "Prompt",
    enableSorting: false,
    cell: ({ row }) => <span className="line-clamp-2 max-w-xl text-sm">{row.original.prompt}</span>,
  },
  {
    accessorKey: "question_type",
    header: "Type",
    cell: ({ row }) => (
      <span className="text-muted-foreground text-xs">{row.original.question_type ?? "—"}</span>
    ),
  },
  {
    accessorKey: "difficulty",
    header: ({ column }) => (
      <Button
        variant="ghost"
        size="sm"
        className="-ml-3"
        onClick={() => column.toggleSorting(column.getIsSorted() === "asc")}
      >
        Difficulty <ArrowUpDown className="size-3" />
      </Button>
    ),
    cell: ({ row }) => (
      <Badge variant={DIFFICULTY_VARIANT[row.original.difficulty]}>{row.original.difficulty}</Badge>
    ),
  },
  {
    accessorKey: "status",
    header: "Status",
    cell: ({ row }) => (
      <Badge variant={STATUS_VARIANT[row.original.status]}>
        {row.original.status.replace(/_/g, " ")}
      </Badge>
    ),
  },
];

export function QuestionsBrowser() {
  const [status, setStatus] = useQueryState("status", parseAsStringLiteral(STATUSES));
  const [limit] = useQueryState("limit", parseAsInteger.withDefault(50));
  const [sorting, setSorting] = useState<SortingState>([]);

  const params = useMemo(() => ({ limit, ...(status ? { status } : {}) }), [limit, status]);
  const { data, isPending, isError, error } = useQuestions(params);

  const table = useReactTable({
    data: data?.questions ?? [],
    columns,
    state: { sorting },
    onSortingChange: setSorting,
    getCoreRowModel: getCoreRowModel(),
    getSortedRowModel: getSortedRowModel(),
  });

  return (
    <>
      <PageHeader
        title="Questions"
        summary="Generate, validate and review Python assessment questions."
        actions={
          <Select
            value={status ?? "all"}
            onValueChange={(value) => setStatus(value === "all" ? null : (value as QuestionStatus))}
          >
            <SelectTrigger className="w-56" size="sm">
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
        }
      />

      {isError ? <QueryError error={error} /> : null}
      {isPending ? <TableSkeleton /> : null}

      {data && data.questions.length === 0 ? (
        <EmptyState
          title="No questions match this filter"
          hint="Generate questions from a book section, or clear the status filter."
        />
      ) : null}

      {data && data.questions.length > 0 ? (
        <>
          <div className="rounded-lg border">
            <Table>
              <TableHeader>
                {table.getHeaderGroups().map((headerGroup) => (
                  <TableRow key={headerGroup.id}>
                    {headerGroup.headers.map((header) => (
                      <TableHead key={header.id}>
                        {header.isPlaceholder
                          ? null
                          : flexRender(header.column.columnDef.header, header.getContext())}
                      </TableHead>
                    ))}
                  </TableRow>
                ))}
              </TableHeader>
              <TableBody>
                {table.getRowModel().rows.map((row) => (
                  <TableRow key={row.id}>
                    {row.getVisibleCells().map((cell) => (
                      <TableCell key={cell.id}>
                        {flexRender(cell.column.columnDef.cell, cell.getContext())}
                      </TableCell>
                    ))}
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          </div>
          <p className="text-muted-foreground text-sm">
            Showing {data.questions.length} of {data.total} questions.
          </p>
        </>
      ) : null}
    </>
  );
}
