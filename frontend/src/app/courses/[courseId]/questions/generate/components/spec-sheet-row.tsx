"use client";

/**
 * One chunk's whole instruction, on one line.
 *
 * Everything a professor decides about a chunk is here and nothing else is: the
 * three counts, the formats they are drawn from, and enough of the chunk's
 * identity to know which chunk it is. Reading the text happens in the preview
 * below the sheet, opened by clicking the row.
 */

import { Check, CircleAlert, Square } from "lucide-react";
import { Badge } from "@/components/ui/badge";
import { TableCell, TableRow } from "@/components/ui/table";
import { Tooltip, TooltipContent, TooltipTrigger } from "@/components/ui/tooltip";
import type { Difficulty, QuestionType } from "@/lib/api/types";
import {
  type ChunkSpec,
  DIFFICULTIES,
  effectiveFormats,
  MAX_COUNT_PER_DIFFICULTY,
  pageLabel,
  type SheetRow,
  specPerFormatTotal,
  specTotal,
} from "../spec-sheet-types";
import { DifficultyStepper } from "./difficulty-stepper";
import { FormatPicker } from "./format-picker";

export function SpecSheetRow({
  row,
  spec,
  defaultFormats,
  isSelected,
  isReading,
  onToggleSelected,
  onRead,
  onCountChange,
  onFormatsChange,
}: {
  row: SheetRow;
  spec: ChunkSpec;
  defaultFormats: readonly QuestionType[];
  isSelected: boolean;
  isReading: boolean;
  onToggleSelected: () => void;
  onRead: () => void;
  onCountChange: (difficulty: Difficulty, value: number) => void;
  onFormatsChange: (formats: QuestionType[] | null) => void;
}) {
  const perFormat = specPerFormatTotal(spec);
  const total = specTotal(spec, defaultFormats);
  const formats = effectiveFormats(spec, defaultFormats);
  const inherited = spec.formats === null;

  return (
    <TableRow
      data-state={isReading ? "selected" : undefined}
      className={[
        "border-border/60 border-b",
        total > 0 ? "bg-accent/25" : "odd:bg-background even:bg-muted/15",
        row.selectable ? "" : "opacity-60",
      ].join(" ")}
    >
      <TableCell className="py-1.5">
        <button
          type="button"
          onClick={onToggleSelected}
          aria-label={`${isSelected ? "Deselect" : "Select"} ${row.title}`}
          aria-pressed={isSelected}
          className="grid size-4 place-items-center rounded-sm border border-border text-primary-foreground transition-colors data-[on=true]:border-primary data-[on=true]:bg-primary"
          data-on={isSelected}
        >
          {isSelected ? <Check className="size-3" /> : <Square className="size-3 opacity-0" />}
        </button>
      </TableCell>

      <TableCell className="py-1.5">
        <button
          type="button"
          onClick={onRead}
          className="max-w-80 text-left underline-offset-4 hover:text-primary hover:underline"
        >
          <span className="block truncate font-medium text-sm">{row.title}</span>
          <span className="block font-mono text-[0.68rem] text-muted-foreground">
            {row.chapterLabel} · {pageLabel(row)}
          </span>
        </button>
      </TableCell>

      <TableCell className="py-1.5 text-muted-foreground text-xs">{row.bookTitle}</TableCell>

      <TableCell className="py-1.5 text-right font-mono text-muted-foreground text-xs tabular-nums">
        {row.charCount.toLocaleString()}
      </TableCell>

      <TableCell className="py-1.5">
        <FormatPicker
          value={formats}
          inherited={inherited}
          disabled={!row.selectable}
          onChange={(next) => onFormatsChange(next)}
          onInherit={() => onFormatsChange(null)}
        />
      </TableCell>

      {DIFFICULTIES.map((difficulty) => (
        <TableCell key={difficulty} className="border-border/60 border-l py-1.5 text-center">
          <DifficultyStepper
            value={spec[difficulty]}
            max={MAX_COUNT_PER_DIFFICULTY}
            disabled={!row.selectable}
            label={`${difficulty} questions from ${row.title}`}
            onChange={(value) => onCountChange(difficulty, value)}
          />
        </TableCell>
      ))}

      {/* The multiplication is shown, not implied: a row asking for 3 in 2 formats
          reads "6" over "3 x 2", so the total is never a surprise. */}
      <TableCell className="py-1.5 text-right">
        {total > 0 ? (
          <span className="flex flex-col items-end leading-tight">
            <span className="font-mono font-semibold text-primary text-sm tabular-nums">
              {total}
            </span>
            {formats.length > 1 ? (
              <span className="font-mono text-[0.6rem] text-muted-foreground tabular-nums">
                {perFormat} x {formats.length}
              </span>
            ) : null}
          </span>
        ) : (
          <span className="font-mono text-muted-foreground text-sm tabular-nums">0</span>
        )}
      </TableCell>

      <TableCell className="py-1.5">
        <div className="flex items-center justify-end gap-1.5">
          {row.existingQuestionCount > 0 ? (
            <Badge variant="secondary" className="font-mono text-[0.65rem]">
              {row.existingQuestionCount} made
            </Badge>
          ) : null}
          {row.isUnlabelled ? (
            <Tooltip>
              <TooltipTrigger asChild>
                <Badge variant="outline" className="text-[0.65rem]">
                  unlabelled
                </Badge>
              </TooltipTrigger>
              <TooltipContent>
                The source declared no heading for this passage. It is labelled by its printed
                location instead.
              </TooltipContent>
            </Tooltip>
          ) : null}
          {row.selectable ? null : (
            <Tooltip>
              <TooltipTrigger asChild>
                <CircleAlert className="size-3.5 text-destructive" />
              </TooltipTrigger>
              <TooltipContent>
                This chunk has no text, so there is nothing to generate from.
              </TooltipContent>
            </Tooltip>
          )}
        </div>
      </TableCell>
    </TableRow>
  );
}
