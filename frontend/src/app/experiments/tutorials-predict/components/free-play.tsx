"use client";

/**
 * Experiment 4: free play. Three boxes (start, stop, step) and the real `list(range(...))` next to
 * them, live, with a small challenge that is checked as the student types. Bad input is described
 * in plain words instead of failing: an empty box, a decimal, a step of 0 (which Python refuses with
 * a ValueError), and a huge range (only the first 20 items are drawn, then "and N more").
 */

import { ArrowRight, CircleCheck } from "lucide-react";
import { useEffect, useId, useRef, useState } from "react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import {
  CHALLENGE_TARGET,
  challengeInsight,
  FREE_PLAY_DEFAULTS,
  type FieldName,
  type FreePlayOutcome,
  formatCount,
  formatList,
  parseFreePlay,
} from "../mock-data";
import { CodeBox } from "./parts";

const FIELDS: { name: FieldName; label: string }[] = [
  { name: "start", label: "Start" },
  { name: "stop", label: "Stop" },
  { name: "step", label: "Step" },
];

export function FreePlay({
  onFinish,
  focusHeading,
}: {
  onFinish: () => void;
  focusHeading: boolean;
}) {
  const headingRef = useRef<HTMLHeadingElement>(null);
  const resultId = useId();
  const [values, setValues] = useState<Record<FieldName, string>>(FREE_PLAY_DEFAULTS);
  const outcome = parseFreePlay(values);
  const invalid = new Set<FieldName>(outcome.status === "ok" ? [] : outcome.fields);
  const solved = outcome.status === "ok" && outcome.hasTarget;

  useEffect(() => {
    if (focusHeading) headingRef.current?.focus();
  }, [focusHeading]);

  return (
    <div className="grid gap-4">
      <h2
        ref={headingRef}
        tabIndex={-1}
        className="rounded font-heading font-semibold text-xl outline-none focus-visible:ring-3 focus-visible:ring-ring/50"
      >
        Try your own
      </h2>

      <div className="grid grid-cols-3 gap-3">
        {FIELDS.map(({ name, label }) => (
          <div key={name} className="grid gap-1.5">
            <Label htmlFor={`${resultId}-${name}`}>{label}</Label>
            <Input
              id={`${resultId}-${name}`}
              type="text"
              inputMode="numeric"
              autoComplete="off"
              maxLength={17}
              value={values[name]}
              aria-invalid={invalid.has(name) ? true : undefined}
              aria-describedby={resultId}
              className="h-10 font-mono"
              onChange={(event) => setValues((current) => ({ ...current, [name]: event.target.value }))}
            />
          </div>
        ))}
      </div>

      <CodeBox
        code={`list(range(${values.start.trim() || "?"}, ${values.stop.trim() || "?"}, ${values.step.trim() || "?"}))`}
        label="Python call"
      />

      <div id={resultId} role="status" aria-label="Result" aria-atomic="true" className="grid gap-1">
        <Result outcome={outcome} />
      </div>

      <div className="grid gap-2 border-border border-t pt-4">
        <p className="font-medium">Can you get {CHALLENGE_TARGET} into the list?</p>
        <div role="status" aria-label="Challenge" className="min-h-6">
          {solved ? (
            <p className="flex items-start gap-2 text-primary">
              <CircleCheck className="mt-0.5 size-4 shrink-0" aria-hidden="true" />
              <span>
                {CHALLENGE_TARGET} is in the list.{" "}
                <span className="text-foreground">{challengeInsight(outcome.step)}</span>
              </span>
            </p>
          ) : null}
        </div>
      </div>

      <div>
        <Button type="button" variant={solved ? "default" : "outline"} onClick={onFinish}>
          Recap
          <ArrowRight aria-hidden="true" />
        </Button>
      </div>
    </div>
  );
}

function Result({ outcome }: { outcome: FreePlayOutcome }) {
  if (outcome.status === "incomplete") {
    return <p className="text-muted-foreground text-sm">{outcome.message}</p>;
  }
  if (outcome.status === "error") {
    return (
      <>
        <p className="text-amber-700 text-sm dark:text-amber-300">{outcome.message}</p>
        <p className="break-words font-mono text-muted-foreground text-xs">{outcome.python}</p>
      </>
    );
  }
  return (
    <>
      <pre className="overflow-x-auto whitespace-pre-wrap break-all rounded-lg border border-border bg-muted/50 px-4 py-3 font-mono text-[0.82rem] text-foreground leading-6">
        {formatList(outcome.head, outcome.hidden)}
        {outcome.hidden > BigInt(0) ? (
          <span className="text-muted-foreground"> and {formatCount(outcome.hidden)} more</span>
        ) : null}
      </pre>
      <p className="font-mono text-muted-foreground text-xs">
        {formatCount(outcome.length)} {outcome.length === BigInt(1) ? "number" : "numbers"}
        {outcome.emptyReason ? ` · ${outcome.emptyReason}` : ""}
      </p>
    </>
  );
}
