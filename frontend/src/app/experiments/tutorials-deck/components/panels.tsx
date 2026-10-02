"use client";

/**
 * The panels beside the code. Each one shows a slice of a recorded step: variables, the call stack
 * with each frame's own variables and the value coming back, list boxes with the names pointing at
 * them, which branch was taken, the while-test history, and the printed output.
 */

import { ArrowRight } from "lucide-react";
import type { ReactNode } from "react";
import { cn } from "@/lib/utils";
import type { BranchState, Frame, Step } from "../traces.generated";

export function PanelLabel({ children }: { children: ReactNode }) {
  return (
    <h3 className="font-mono text-[0.68rem] text-muted-foreground uppercase tracking-widest">
      {children}
    </h3>
  );
}

export function Panel({ title, children }: { title: string; children: ReactNode }) {
  return (
    <section className="border-border border-t pt-2.5 first:border-t-0 first:pt-0">
      <PanelLabel>{title}</PanelLabel>
      <div className="mt-1.5">{children}</div>
    </section>
  );
}

function Vars({ vars, before }: { vars: Record<string, string>; before?: Record<string, string> }) {
  const names = Object.keys(vars);
  if (names.length === 0) {
    return <p className="text-muted-foreground text-xs">No variables yet.</p>;
  }
  return (
    <dl className="grid gap-0.5 font-mono text-sm">
      {names.map((name) => (
        <div key={name} className="flex flex-wrap items-baseline gap-x-3">
          <dt className="w-16 shrink-0 text-muted-foreground">{name}</dt>
          <dd
            className={cn(
              "m-0 break-all rounded px-1.5 text-foreground",
              before?.[name] !== vars[name] && "bg-accent font-medium",
            )}
          >
            {vars[name]}
          </dd>
        </div>
      ))}
    </dl>
  );
}

export function VariablesPanel({ step, previous }: { step: Step; previous?: Step }) {
  return (
    <Panel title="Variables">
      <Vars vars={step.frames[0]?.vars ?? {}} before={previous?.frames[0]?.vars} />
    </Panel>
  );
}

function StackFrame({ frame, top, before }: { frame: Frame; top: boolean; before?: Frame }) {
  return (
    <li className={cn("border-l-2 pl-3", top ? "border-primary" : "border-border")}>
      <div className="flex flex-wrap items-baseline gap-x-2">
        <span className="font-medium font-mono text-sm">{frame.label}</span>
        {frame.ret !== undefined ? (
          <span className="rounded bg-accent px-1.5 py-0.5 font-medium font-mono text-xs">
            returns {frame.ret}
          </span>
        ) : null}
      </div>
      <Vars vars={frame.vars} before={before?.vars} />
    </li>
  );
}

/** Top of the stack first, like a stack of plates; the global frame sits at the bottom. */
export function CallStackPanel({ step, previous }: { step: Step; previous?: Step }) {
  const frames = step.frames.map((frame, depth) => ({ frame, depth })).reverse();
  return (
    <Panel title="Call stack">
      <ul className="grid gap-1.5">
        {frames.map(({ frame, depth }) => {
          const earlier = previous?.frames[depth];
          return (
            <StackFrame
              key={`${depth}:${frame.label}`}
              frame={frame}
              top={depth === step.frames.length - 1}
              before={earlier?.label === frame.label ? earlier : undefined}
            />
          );
        })}
      </ul>
    </Panel>
  );
}

export function MemoryPanel({ step }: { step: Step }) {
  const heap = step.heap ?? [];
  return (
    <Panel title="Memory">
      {heap.length === 0 ? <p className="text-muted-foreground text-xs">No lists yet.</p> : null}
      <ul className="grid gap-3">
        {heap.map((object) => (
          <li key={object.id} aria-label={`List ${object.id}, named ${object.names.join(" and ")}`}>
            <div className="flex items-center gap-2">
              <span className="flex shrink-0 flex-col gap-1">
                {object.names.map((name) => (
                  <span
                    key={name}
                    className="rounded border border-border bg-background px-1.5 font-medium font-mono text-sm"
                  >
                    {name}
                  </span>
                ))}
              </span>
              <ArrowRight aria-hidden="true" className="size-4 shrink-0 text-muted-foreground" />
              <ol className="flex min-w-0 flex-wrap gap-1">
                {object.items.map((item, index) => {
                  const focused = step.focus?.obj === object.id && step.focus.index === index;
                  const added = step.added?.some((a) => a.obj === object.id && a.index === index);
                  return (
                    <li
                      // biome-ignore lint/suspicious/noArrayIndexKey: list positions are the point
                      key={index}
                      className="flex flex-col items-center"
                      data-focused={focused ? "true" : undefined}
                    >
                      <span className="font-mono text-[0.65rem] text-muted-foreground">{index}</span>
                      <span
                        className={cn(
                          "min-w-10 rounded border px-1.5 py-0.5 text-center font-mono text-sm",
                          focused ? "border-primary bg-accent ring-2 ring-primary" : "border-border",
                          added && "bg-accent font-semibold",
                        )}
                      >
                        {item}
                      </span>
                    </li>
                  );
                })}
              </ol>
            </div>
            {object.names.length > 1 ? (
              <p className="mt-1 font-medium text-xs">
                {object.names.join(" and ")} are two names for the same list.
              </p>
            ) : null}
          </li>
        ))}
      </ul>
    </Panel>
  );
}

const BRANCH_TEXT: Record<BranchState, string> = {
  taken: "taken",
  false: "false, not taken",
  skipped: "skipped, never tested",
  pending: "not reached yet",
};

export function BranchesPanel({ step }: { step: Step }) {
  return (
    <Panel title="Branches">
      <ul className="grid gap-1 font-mono text-sm">
        {(step.branches ?? []).map((branch) => (
          <li
            key={branch.label}
            data-state={branch.state}
            className={cn(
              "flex flex-wrap items-baseline justify-between gap-x-3 border-l-2 pl-2",
              branch.state === "taken" ? "border-primary" : "border-transparent",
              (branch.state === "skipped" || branch.state === "false") && "text-muted-foreground",
            )}
          >
            <span className={cn(branch.state === "skipped" && "line-through")}>{branch.label}</span>
            <span
              className={cn(
                "font-sans text-xs",
                branch.state === "taken" && "font-medium text-foreground",
              )}
            >
              {BRANCH_TEXT[branch.state]}
            </span>
          </li>
        ))}
      </ul>
    </Panel>
  );
}

export function WhilePanel({ step }: { step: Step }) {
  const check = step.check;
  return (
    <Panel title="Loop test">
      <p className="font-mono text-sm">{check?.expr}</p>
      {check && check.results.length > 0 ? (
        <ol aria-label="Results so far" className="mt-1 flex flex-wrap gap-1">
          {check.results.map((result, index) => (
            <li
              // biome-ignore lint/suspicious/noArrayIndexKey: one chip per check, in order
              key={index}
              className={cn(
                "rounded border px-1.5 py-0.5 font-mono text-xs",
                result ? "border-border" : "border-primary bg-accent font-medium",
              )}
            >
              {index + 1}: {result ? "True" : "False"}
            </li>
          ))}
        </ol>
      ) : (
        <p className="mt-1 text-muted-foreground text-xs">Not checked yet.</p>
      )}
    </Panel>
  );
}

export function OutputPanel({ lines, endless }: { lines: string[]; endless?: boolean }) {
  return (
    <Panel title="Output">
      {/* No aria-live here: the step caption already announces what print did. */}
      <fieldset aria-label="Program output" className="m-0 min-h-6 min-w-0 border-0 p-0 font-mono text-sm leading-6">
        {lines.length === 0 ? (
          <span className="font-sans text-muted-foreground text-xs">Nothing printed yet.</span>
        ) : (
          lines.map((line, index) => (
            <div
              // biome-ignore lint/suspicious/noArrayIndexKey: printed lines only ever append
              key={index}
              data-testid="output-line"
            >
              {line}
            </div>
          ))
        )}
        {endless && lines.length > 0 ? (
          <span className="font-sans text-muted-foreground text-xs">and on, forever</span>
        ) : null}
      </fieldset>
    </Panel>
  );
}
