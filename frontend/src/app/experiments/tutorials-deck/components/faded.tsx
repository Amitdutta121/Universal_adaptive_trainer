"use client";

/**
 * The last card of every deck: the worked example again with the end missing. The student picks
 * the missing line or value, types it, or (for functions) puts shuffled lines in order. Feedback is
 * immediate and one line; a wrong answer can be retried. Getting it right calls `onSolved`.
 *
 * Which answer is right is never typed here: it comes from the recorded run in `mock-data.ts`.
 */

import { Check, Undo2, X } from "lucide-react";
import { type FormEvent, type ReactNode, useState } from "react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { cn } from "@/lib/utils";
import type { FadedTask } from "../mock-data";
import { CodeView } from "./code-view";

type Task<K extends FadedTask["kind"]> = Extract<FadedTask, { kind: K }>;

function Feedback({ ok, children }: { ok: boolean | null; children?: ReactNode }) {
  // Always rendered so the live region exists before its text changes.
  return (
    <div role="status" aria-live="polite" className="min-h-[3rem] text-sm leading-6">
      {ok === null ? null : (
        <p className="flex items-start gap-1.5">
          {ok ? (
            <Check aria-hidden="true" className="mt-1 size-4 shrink-0 text-primary" />
          ) : (
            <X aria-hidden="true" className="mt-1 size-4 shrink-0 text-destructive" />
          )}
          <span>{children}</span>
        </p>
      )}
    </div>
  );
}

function Layout({ code, children }: { code: ReactNode; children: ReactNode }) {
  return (
    <div className="grid gap-4 md:grid-cols-[minmax(0,1.1fr)_minmax(0,1fr)] md:items-start md:gap-6">
      <div className="min-w-0">{code}</div>
      <div className="min-w-0 space-y-3">{children}</div>
    </div>
  );
}

// ---- pick ------------------------------------------------------------------------------------

export function FadedPick({ task, onSolved }: { task: Task<"pick">; onSolved: () => void }) {
  const [chosen, setChosen] = useState<string | null>(null);
  const picked = task.choices.find((choice) => choice.value === chosen);
  const solved = chosen !== null && chosen === task.answer;
  const hasBlank = task.code.includes("____");
  const code = hasBlank ? task.code.replace("____", chosen ?? "____") : task.code;
  const blankLine = hasBlank ? task.code.split("\n").findIndex((l) => l.includes("____")) + 1 : null;

  const choose = (value: string) => {
    if (solved) return;
    setChosen(value);
    if (value === task.answer) onSolved();
  };

  return (
    <Layout code={<CodeView label="Code with a missing part" code={code} current={blankLine} />}>
      <fieldset aria-label={task.ask} className="m-0 grid min-w-0 gap-2 border-0 p-0">
        <p className="font-medium">{task.ask}</p>
        <div className="flex flex-wrap gap-2">
          {task.choices.map((choice) => (
            <Button
              key={choice.value}
              type="button"
              variant="outline"
              disabled={solved && choice.value !== chosen}
              aria-pressed={choice.value === chosen}
              onClick={() => choose(choice.value)}
              className={cn(
                "font-mono",
                choice.value === chosen && (solved ? "border-primary bg-accent" : "border-destructive"),
              )}
            >
              {choice.value}
            </Button>
          ))}
        </div>
      </fieldset>
      <Feedback ok={picked ? solved : null}>
        <strong className="font-semibold">{solved ? "Right. " : "Not quite. "}</strong>
        {picked?.why}
        {picked?.result ? <span className="block text-muted-foreground">{picked.result}</span> : null}
      </Feedback>
    </Layout>
  );
}

// ---- type ------------------------------------------------------------------------------------

const squash = (text: string) => text.replace(/\s+/g, "");

export function FadedType({ task, onSolved }: { task: Task<"type">; onSolved: () => void }) {
  const [value, setValue] = useState("");
  const [state, setState] = useState<"idle" | "wrong" | "right">("idle");
  const [tries, setTries] = useState(0);

  const submit = (event: FormEvent) => {
    event.preventDefault();
    if (state === "right" || value.trim() === "") return;
    setTries((count) => count + 1);
    if (squash(value) === squash(task.answer)) {
      setState("right");
      onSolved();
    } else setState("wrong");
  };

  return (
    <Layout code={<CodeView label="Code" code={task.code} />}>
      <form onSubmit={submit} className="grid gap-2">
        <label htmlFor="faded-answer" className="font-medium">
          {task.ask}
        </label>
        <div className="flex gap-2">
          <Input
            id="faded-answer"
            value={value}
            onChange={(event) => setValue(event.target.value)}
            disabled={state === "right"}
            autoComplete="off"
            spellCheck={false}
            className="max-w-56 font-mono"
          />
          <Button type="submit" disabled={state === "right"}>
            Check
          </Button>
        </div>
      </form>
      <Feedback ok={state === "idle" ? null : state === "right"}>
        {state === "right" ? (
          <>
            <strong className="font-semibold">Right. </strong>
            {task.why}
          </>
        ) : (
          <>
            <strong className="font-semibold">Not quite. </strong>
            {task.retry}
            {tries >= 2 ? (
              <span className="block text-muted-foreground">
                The answer is <code className="font-mono">{task.answer}</code>.
              </span>
            ) : null}
          </>
        )}
      </Feedback>
    </Layout>
  );
}

// ---- parsons ---------------------------------------------------------------------------------

export function FadedParsons({ task, onSolved }: { task: Task<"parsons">; onSolved: () => void }) {
  /** Indices into `task.lines`, in the order the student tapped them. */
  const [placed, setPlaced] = useState<number[]>([]);
  const complete = placed.length === task.lines.length;
  const result = complete ? task.orders[placed.join(",")] : undefined;
  const solved = result?.ok === true;
  const bank = task.shuffled.filter((index) => !placed.includes(index));

  const place = (index: number) => {
    if (complete) return;
    const next = [...placed, index];
    setPlaced(next);
    if (next.length === task.lines.length && task.orders[next.join(",")]?.ok) onSolved();
  };

  return (
    <Layout
      code={
        <div className="grid gap-2">
          <p className="font-medium">Lines to place</p>
          <ul className="grid gap-1.5">
            {bank.map((index) => (
              <li key={index}>
                <button
                  type="button"
                  onClick={() => place(index)}
                  className="w-full rounded-lg border border-border bg-muted/50 px-3 py-1.5 text-left font-mono text-sm outline-none hover:bg-muted focus-visible:ring-3 focus-visible:ring-ring/50"
                >
                  <span className="whitespace-pre">{task.lines[index]}</span>
                </button>
              </li>
            ))}
            {bank.length === 0 ? (
              <li className="text-muted-foreground text-xs">All lines placed.</li>
            ) : null}
          </ul>
        </div>
      }
    >
      <div className="grid gap-2">
        <p className="font-medium" id="parsons-mine">
          {task.ask}
        </p>
        <ol aria-labelledby="parsons-mine" className="grid min-h-[6.5rem] gap-1.5">
          {placed.map((index, position) => (
            <li key={index}>
              <button
                type="button"
                disabled={solved}
                aria-label={`Remove line ${position + 1}: ${task.lines[index].trim()}`}
                onClick={() => setPlaced(placed.filter((other) => other !== index))}
                className="flex w-full items-center gap-2 rounded-lg border border-border px-3 py-1.5 text-left font-mono text-sm outline-none hover:bg-muted focus-visible:ring-3 focus-visible:ring-ring/50 disabled:pointer-events-none"
              >
                <span aria-hidden="true" className="w-3 text-muted-foreground text-xs">
                  {position + 1}
                </span>
                <span className="whitespace-pre">{task.lines[index]}</span>
              </button>
            </li>
          ))}
          {placed.length === 0 ? (
            <li className="text-muted-foreground text-xs">Tap a line to start.</li>
          ) : null}
        </ol>
        {placed.length > 0 && !solved ? (
          <Button
            type="button"
            variant="ghost"
            size="sm"
            className="w-fit"
            onClick={() => setPlaced([])}
          >
            <Undo2 aria-hidden="true" />
            Start over
          </Button>
        ) : null}
      </div>
      <Feedback ok={result ? solved : null}>
        {solved ? (
          <>
            <strong className="font-semibold">Right. </strong>
            {task.why} It prints {task.output.join(" ")}.
          </>
        ) : (
          <>
            <strong className="font-semibold">Not yet. </strong>
            Python says: {result?.text} Try another order.
          </>
        )}
      </Feedback>
    </Layout>
  );
}
