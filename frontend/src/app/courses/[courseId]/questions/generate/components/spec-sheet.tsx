"use client";

/**
 * The sheet itself: one row per chunk, three difficulty columns, totals underneath.
 *
 * The column totals are the reason this is a table rather than a list of cards.
 * They answer the question a professor filling a chapter actually has — "have I
 * asked for anything hard?" — without leaving the screen.
 */

import { CheckCheck } from "lucide-react";
import { Button } from "@/components/ui/button";
import {
  Table,
  TableBody,
  TableCell,
  TableFooter,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import type { Difficulty, QuestionType } from "@/lib/api/types";
import {
  type ChunkSpec,
  DIFFICULTIES,
  effectiveFormats,
  type SheetRow,
  specTotal,
} from "../spec-sheet-types";
import { SpecSheetRow } from "./spec-sheet-row";

const DIFFICULTY_HEAD: Record<Difficulty, string> = {
  easy: "text-[color:var(--ok-solid)]",
  medium: "text-primary",
  hard: "text-[color:var(--warn-solid)]",
};

export function SpecSheet({
  rows,
  specFor,
  defaultFormats,
  selectedIds,
  readingSectionId,
  onToggleSelected,
  onSelectAllVisible,
  onRead,
  onCountChange,
  onFormatsChange,
}: {
  rows: readonly SheetRow[];
  specFor: (sectionId: number) => ChunkSpec;
  defaultFormats: readonly QuestionType[];
  selectedIds: ReadonlySet<number>;
  readingSectionId: number | null;
  onToggleSelected: (sectionId: number) => void;
  onSelectAllVisible: (selected: boolean) => void;
  onRead: (row: SheetRow) => void;
  onCountChange: (sectionId: number, difficulty: Difficulty, value: number) => void;
  onFormatsChange: (sectionId: number, formats: QuestionType[] | null) => void;
}) {
  const allVisibleSelected = rows.length > 0 && rows.every((row) => selectedIds.has(row.sectionId));

  const columnTotal = (difficulty: Difficulty) =>
    rows.reduce((sum, row) => {
      const spec = specFor(row.sectionId);
      return sum + spec[difficulty] * effectiveFormats(spec, defaultFormats).length;
    }, 0);
  const sheetTotal = rows.reduce(
    (sum, row) => sum + specTotal(specFor(row.sectionId), defaultFormats),
    0,
  );

  return (
    <div className="max-h-[52vh] overflow-auto">
      <Table className="table-auto">
        <TableHeader>
          <TableRow className="hover:bg-transparent">
            <TableHead className="sticky top-0 z-10 w-8 bg-background/95 backdrop-blur">
              <Button
                type="button"
                variant="ghost"
                size="icon"
                className="size-5 text-muted-foreground"
                aria-label={allVisibleSelected ? "Deselect all shown" : "Select all shown"}
                onClick={() => onSelectAllVisible(!allVisibleSelected)}
              >
                <CheckCheck className="size-3.5" />
              </Button>
            </TableHead>
            <HeadCell>Chunk</HeadCell>
            <HeadCell>Book</HeadCell>
            <HeadCell align="right">Chars</HeadCell>
            <HeadCell>Formats to draw from</HeadCell>
            {DIFFICULTIES.map((difficulty) => (
              <HeadCell key={difficulty} align="center" className={DIFFICULTY_HEAD[difficulty]}>
                {difficulty}
              </HeadCell>
            ))}
            <HeadCell align="right">Row</HeadCell>
            <HeadCell align="right">State</HeadCell>
          </TableRow>
        </TableHeader>

        <TableBody>
          {rows.map((row) => (
            <SpecSheetRow
              key={row.sectionId}
              row={row}
              spec={specFor(row.sectionId)}
              defaultFormats={defaultFormats}
              isSelected={selectedIds.has(row.sectionId)}
              isReading={readingSectionId === row.sectionId}
              onToggleSelected={() => onToggleSelected(row.sectionId)}
              onRead={() => onRead(row)}
              onCountChange={(difficulty, value) => onCountChange(row.sectionId, difficulty, value)}
              onFormatsChange={(formats) => onFormatsChange(row.sectionId, formats)}
            />
          ))}
        </TableBody>

        <TableFooter className="sticky bottom-0 bg-muted/60 backdrop-blur">
          <TableRow className="hover:bg-transparent">
            <TableCell colSpan={5} className="text-right font-medium text-xs">
              Questions each column will produce, for the {rows.length} chunks shown
            </TableCell>
            {DIFFICULTIES.map((difficulty) => (
              <TableCell
                key={difficulty}
                className="border-border/60 border-l text-center font-mono text-sm tabular-nums"
              >
                {columnTotal(difficulty)}
              </TableCell>
            ))}
            <TableCell className="text-right font-mono font-semibold text-primary text-sm tabular-nums">
              {sheetTotal}
            </TableCell>
            <TableCell />
          </TableRow>
        </TableFooter>
      </Table>
    </div>
  );
}

function HeadCell({
  children,
  align = "left",
  className = "",
}: {
  children: React.ReactNode;
  align?: "left" | "center" | "right";
  className?: string;
}) {
  const alignment =
    align === "right" ? "text-right" : align === "center" ? "text-center" : "text-left";
  return (
    <TableHead
      className={`sticky top-0 z-10 bg-background/95 py-2 font-mono text-[0.65rem] uppercase tracking-[0.14em] backdrop-blur ${alignment} ${className}`}
    >
      {children}
    </TableHead>
  );
}
