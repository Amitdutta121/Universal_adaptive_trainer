"use client";

/**
 * The filter bar pieces shared by the course's filterable tables (Questions,
 * Students): a "Label: value" dropdown button per filter, and the "Active view"
 * strip of removable chips under it.
 */

import { ChevronDown, X } from "lucide-react";
import { Button } from "@/components/ui/button";
import {
  DropdownMenu,
  DropdownMenuCheckboxItem,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuRadioGroup,
  DropdownMenuRadioItem,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";

export function FilterLabel({ children }: { children: string }) {
  return (
    <span className="font-mono text-[0.67rem] text-muted-foreground uppercase tracking-[0.16em]">
      {children}
    </span>
  );
}

/**
 * One filter as a button that names the filter and what it keeps ("Status: Approved +1"),
 * opening a checklist so several values can be kept at once. The menu stays open while
 * ticking; no values ticked means the filter is off. `capitalize` is for enum labels;
 * names an instructor typed (topics) are shown as written.
 */
export function FilterMultiSelect<T extends string | number>({
  label,
  allLabel,
  value,
  options,
  onChange,
  capitalize = true,
  disabled = false,
}: {
  label: string;
  allLabel: string;
  value: readonly T[];
  options: readonly { value: T; label: string; count?: number }[];
  onChange: (value: T[]) => void;
  capitalize?: boolean;
  disabled?: boolean;
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
        <Button
          variant="outline"
          className="h-9 min-w-40 max-w-72 justify-between font-normal"
          disabled={disabled}
        >
          <span className="truncate">
            <span className="text-muted-foreground">{label}:</span>{" "}
            {chosen.length === 0 ? (
              allLabel
            ) : (
              <span className={capitalize ? "capitalize" : undefined}>
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
      <DropdownMenuContent align="start" className="max-h-80 min-w-56 overflow-y-auto">
        {options.map((option) => (
          <DropdownMenuCheckboxItem
            key={option.value}
            checked={value.includes(option.value)}
            onCheckedChange={(on) => toggle(option.value, on)}
            onSelect={(event) => event.preventDefault()}
            className={capitalize ? "capitalize" : undefined}
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

export function ActiveFilterChip({
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

/**
 * A single-choice filter with the same trigger as `FilterMultiSelect`, for filters
 * whose values are mutually exclusive ranges. `allValue` is the "off" option.
 */
export function FilterSelect<T extends string>({
  label,
  value,
  allValue,
  options,
  onChange,
}: {
  label: string;
  value: T;
  allValue: T;
  options: readonly { value: T; label: string }[];
  onChange: (value: T) => void;
}) {
  const chosen = options.find((option) => option.value === value);
  return (
    <DropdownMenu>
      <DropdownMenuTrigger asChild>
        <Button variant="outline" className="h-9 min-w-40 max-w-72 justify-between font-normal">
          <span className="truncate">
            <span className="text-muted-foreground">{label}:</span> {chosen?.label ?? value}
          </span>
          <ChevronDown className="size-4 text-muted-foreground" />
        </Button>
      </DropdownMenuTrigger>
      <DropdownMenuContent align="start" className="max-h-80 min-w-56 overflow-y-auto">
        <DropdownMenuRadioGroup value={value} onValueChange={(next) => onChange(next as T)}>
          {options.map((option) => (
            <DropdownMenuRadioItem key={option.value} value={option.value}>
              {option.label}
            </DropdownMenuRadioItem>
          ))}
        </DropdownMenuRadioGroup>
        {value !== allValue ? (
          <>
            <DropdownMenuSeparator />
            <DropdownMenuItem onSelect={() => onChange(allValue)}>
              Clear {label.toLowerCase()}
            </DropdownMenuItem>
          </>
        ) : null}
      </DropdownMenuContent>
    </DropdownMenu>
  );
}
