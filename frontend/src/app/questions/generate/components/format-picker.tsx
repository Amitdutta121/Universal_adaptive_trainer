"use client";

/**
 * Which formats a chunk's questions may be drawn from.
 *
 * Choosing three formats does not triple the count: the counts say how many
 * questions, this says what they may be. The API hands them out round-robin.
 *
 * Used twice — once for the sheet default, once per row — so it carries the
 * inherit/override distinction itself: a row showing the default renders it in
 * muted italics, and "Follow the sheet default" clears the override.
 */

import { ChevronDown } from "lucide-react";
import { Button } from "@/components/ui/button";
import {
  DropdownMenu,
  DropdownMenuCheckboxItem,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuLabel,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import type { QuestionType } from "@/lib/api/types";
import { QUESTION_TYPE_LABEL, QUESTION_TYPE_SHORT, QUESTION_TYPES } from "../spec-sheet-types";

export function FormatPicker({
  value,
  onChange,
  inherited = false,
  onInherit,
  disabled = false,
  triggerLabel,
}: {
  /** The formats in force — a row's own, or the default it inherits. */
  value: readonly QuestionType[];
  onChange: (formats: QuestionType[]) => void;
  /** True when `value` came from the sheet default rather than this chunk. */
  inherited?: boolean;
  /** Offered only where inheriting is possible, so the sheet default has no reset. */
  onInherit?: () => void;
  disabled?: boolean;
  triggerLabel?: string;
}) {
  const summary =
    value.length === 0
      ? "No format"
      : value.length <= 2
        ? value.map((format) => QUESTION_TYPE_SHORT[format]).join(", ")
        : `${QUESTION_TYPE_SHORT[value[0]]} +${value.length - 1}`;

  const toggle = (format: QuestionType, checked: boolean) => {
    const next = checked ? [...value, format] : value.filter((entry) => entry !== format);
    // Ordered by the canonical list rather than by click order, so two chunks with
    // the same formats always read the same way.
    onChange(QUESTION_TYPES.filter((entry) => next.includes(entry)));
  };

  return (
    <DropdownMenu>
      <DropdownMenuTrigger asChild>
        <Button
          type="button"
          variant="outline"
          size="sm"
          disabled={disabled}
          className={[
            "h-7 justify-between gap-1 border-border/80 px-2 font-normal text-xs",
            inherited ? "text-muted-foreground italic" : "",
          ].join(" ")}
        >
          {triggerLabel ?? summary}
          <ChevronDown className="size-3 opacity-60" />
        </Button>
      </DropdownMenuTrigger>
      <DropdownMenuContent align="start" className="w-56">
        <DropdownMenuLabel>Formats to draw from</DropdownMenuLabel>
        <DropdownMenuSeparator />
        {QUESTION_TYPES.map((format) => (
          <DropdownMenuCheckboxItem
            key={format}
            checked={value.includes(format)}
            onCheckedChange={(checked) => toggle(format, Boolean(checked))}
            onSelect={(event) => event.preventDefault()}
          >
            {QUESTION_TYPE_LABEL[format]}
          </DropdownMenuCheckboxItem>
        ))}
        {onInherit ? (
          <>
            <DropdownMenuSeparator />
            <DropdownMenuItem disabled={inherited} onSelect={() => onInherit()}>
              Follow the sheet default
            </DropdownMenuItem>
          </>
        ) : null}
      </DropdownMenuContent>
    </DropdownMenu>
  );
}
