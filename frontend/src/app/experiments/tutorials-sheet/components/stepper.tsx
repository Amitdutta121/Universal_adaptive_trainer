"use client";

import { Minus, Plus } from "lucide-react";
import { Button } from "@/components/ui/button";

/** A small "- 3 +" control. Real buttons with names that say what they change and to which side. */
export function Stepper({
  name,
  value,
  min,
  max,
  onChange,
}: {
  name: string;
  value: number;
  min: number;
  max: number;
  onChange: (next: number) => void;
}) {
  return (
    <fieldset aria-label={name} className="flex min-w-0 items-center gap-2">
      <span className="w-9 font-mono text-muted-foreground text-xs">{name}</span>
      <Button
        type="button"
        variant="outline"
        size="icon"
        aria-label={`Decrease ${name}`}
        disabled={value <= min}
        onClick={() => onChange(value - 1)}
      >
        <Minus aria-hidden="true" />
      </Button>
      <span
        data-testid={`${name}-value`}
        className="w-6 text-center font-medium font-mono text-foreground tabular-nums"
      >
        {value}
      </span>
      <Button
        type="button"
        variant="outline"
        size="icon"
        aria-label={`Increase ${name}`}
        disabled={value >= max}
        onClick={() => onChange(value + 1)}
      >
        <Plus aria-hidden="true" />
      </Button>
    </fieldset>
  );
}
