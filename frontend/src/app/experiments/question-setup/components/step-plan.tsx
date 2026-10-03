"use client";

/**
 * Step 4 · Plan. The blueprint: every subtopic x difficulty cell, what the bank already has,
 * and what the chosen styles will add to reach the floor. The professor can leave subtopics out,
 * then generate.
 */

import { ChevronRightIcon, InfoIcon, TriangleAlertIcon } from "lucide-react";
import { useState } from "react";
import { cn } from "@/lib/utils";
import { DIFFICULTIES, type Difficulty, type Domain, type Template } from "../mock-types";
import { EXPECTED_APPROVAL, FLOOR_PER_CELL, type Plan, type PlanCell } from "../plan";
import { DifficultyBadge, TypeBadge } from "./badges";

function CellView({ cell, templateName }: { cell: PlanCell; templateName(id: string): string }) {
  if (cell.blocked) {
    return (
      <span
        className="inline-flex items-center gap-1 text-[var(--warn-solid)] text-xs"
        title={
          cell.blocked === "no-style"
            ? "No style chosen at this difficulty"
            : "None of your styles at this difficulty can be used for this topic"
        }
      >
        <TriangleAlertIcon className="size-3.5" aria-hidden />
        {cell.have} · {cell.blocked === "no-style" ? "no style" : "no usable style"}
      </span>
    );
  }
  if (cell.add === 0) {
    return <span className="text-muted-foreground text-xs tabular-nums">{cell.have} ✓</span>;
  }
  return (
    <span
      className="text-xs tabular-nums"
      title={cell.mix.map((entry) => `${templateName(entry.templateId)} ×${entry.count}`).join("\n")}
    >
      <span className="text-muted-foreground">{cell.have} →</span>{" "}
      <span className="font-medium text-[var(--accent-text)]">+{cell.add}</span>
    </span>
  );
}

function sumAdd(cells: readonly Record<Difficulty, PlanCell>[], difficulty: Difficulty) {
  return cells.reduce((sum, cell) => sum + cell[difficulty].add, 0);
}

export function StepPlan({
  domain,
  deck,
  plan,
  excluded,
  onToggleExcluded,
  generated,
}: {
  domain: Domain;
  deck: readonly Template[];
  plan: Plan;
  excluded: ReadonlySet<string>;
  onToggleExcluded(subtopicId: string): void;
  generated: boolean;
}) {
  const [open, setOpen] = useState<Set<string>>(() => new Set(domain.topics.slice(0, 2).map((t) => t.id)));
  const byId = new Map(deck.map((template) => [template.id, template]));
  const templateName = (id: string) => byId.get(id)?.name ?? id;

  function toggle(topicId: string) {
    setOpen((prev) => {
      const next = new Set(prev);
      if (next.has(topicId)) next.delete(topicId);
      else next.add(topicId);
      return next;
    });
  }

  const stats = [
    { label: "New questions needed", value: plan.totalAdd.toLocaleString() },
    {
      label: `Drafts to write (≈${Math.round(EXPECTED_APPROVAL * 100)}% get approved)`,
      value: plan.drafts.toLocaleString(),
    },
    { label: "Estimated cost", value: `$${plan.costUsd.toFixed(2)}` },
    { label: "Estimated time", value: `~${plan.minutes} min` },
  ];

  return (
    <div className="flex flex-col gap-6">
      <p className="text-muted-foreground text-sm">
        Students are served a subtopic first, then a difficulty that matches their mastery. Each subtopic needs at
        least {FLOOR_PER_CELL} approved questions at every difficulty, or students repeat questions or get the wrong
        level. {plan.cellsReady} of {plan.cellsTotal} cells can reach that with your styles.
      </p>

      <dl className="grid grid-cols-2 gap-px overflow-hidden rounded-lg border bg-border md:grid-cols-4">
        {stats.map((stat) => (
          <div key={stat.label} className="flex flex-col gap-0.5 bg-card px-3.5 py-3">
            <dt className="text-muted-foreground text-xs">{stat.label}</dt>
            <dd className="font-semibold text-lg tabular-nums">{stat.value}</dd>
          </div>
        ))}
      </dl>

      {plan.blockedCells > 0 ? (
        <div
          role="alert"
          className="flex items-start gap-3 rounded-lg border border-[var(--warn-solid)]/50 bg-[var(--warn-wash)] p-3 text-sm"
        >
          <TriangleAlertIcon className="mt-0.5 size-4 shrink-0 text-[var(--warn-solid)]" aria-hidden />
          <p>
            {plan.blockedCells} {plan.blockedCells === 1 ? "cell" : "cells"} cannot be filled with the styles you
            chose. Students will get another difficulty there. Go back to <strong>Question styles</strong> to add
            one, or leave those subtopics out.
          </p>
        </div>
      ) : null}

      <div className="overflow-x-auto rounded-lg border">
        <table className="w-full min-w-[640px] text-sm">
          <thead>
            <tr className="border-b bg-muted/40 text-left">
              <th scope="col" className="px-3 py-2 font-medium">
                Subtopic
              </th>
              {DIFFICULTIES.map((difficulty) => (
                <th key={difficulty} scope="col" className="w-28 px-3 py-2 font-medium">
                  <DifficultyBadge difficulty={difficulty} />
                </th>
              ))}
              <th scope="col" className="w-20 px-3 py-2 text-right font-medium">
                Include
              </th>
            </tr>
          </thead>
          <tbody>
            {plan.topics.map(({ topic, subtopics }) => {
              const isOpen = open.has(topic.id);
              const cells = subtopics.filter((row) => !row.excluded).map((row) => row.cells);
              const blocked = cells.reduce(
                (sum, row) => sum + DIFFICULTIES.filter((d) => row[d].blocked).length,
                0,
              );
              return [
                <tr key={topic.id} className="border-b bg-muted/20">
                  <th scope="rowgroup" className="px-3 py-2 text-left font-medium">
                    <button
                      type="button"
                      aria-expanded={isOpen}
                      onClick={() => toggle(topic.id)}
                      className="flex items-center gap-1.5 rounded-sm text-left outline-none focus-visible:ring-3 focus-visible:ring-ring/50"
                    >
                      <ChevronRightIcon
                        className={cn("size-4 text-muted-foreground transition-transform", isOpen && "rotate-90")}
                        aria-hidden
                      />
                      {topic.name}
                      <span className="font-normal text-muted-foreground text-xs">· {topic.subtopics.length}</span>
                    </button>
                  </th>
                  {DIFFICULTIES.map((difficulty) => {
                    const add = sumAdd(cells, difficulty);
                    return (
                      <td key={difficulty} className="px-3 py-2 text-xs tabular-nums">
                        {add > 0 ? <span className="font-medium text-[var(--accent-text)]">+{add}</span> : null}
                      </td>
                    );
                  })}
                  <td className="px-3 py-2 text-right text-xs">
                    {blocked > 0 ? (
                      <span className="text-[var(--warn-solid)]">
                        {blocked} unfilled
                      </span>
                    ) : null}
                  </td>
                </tr>,
                ...(isOpen
                  ? subtopics.map(({ subtopic, excluded: isExcluded, cells: row }) => (
                      <tr key={subtopic.id} className={cn("border-b last:border-0", isExcluded && "opacity-50")}>
                        <td className="py-1.5 pr-3 pl-9">{subtopic.name}</td>
                        {DIFFICULTIES.map((difficulty) => (
                          <td key={difficulty} className="px-3 py-1.5">
                            {isExcluded ? (
                              <span className="text-muted-foreground text-xs">left out</span>
                            ) : (
                              <CellView cell={row[difficulty]} templateName={templateName} />
                            )}
                          </td>
                        ))}
                        <td className="px-3 py-1.5 text-right">
                          <input
                            type="checkbox"
                            className="size-4 accent-[var(--accent-solid)]"
                            checked={!excluded.has(subtopic.id)}
                            onChange={() => onToggleExcluded(subtopic.id)}
                            aria-label={`Include ${subtopic.name}`}
                          />
                        </td>
                      </tr>
                    ))
                  : []),
              ];
            })}
          </tbody>
        </table>
      </div>
      <p className="-mt-4 text-muted-foreground text-xs">
        “2 → +1” means 2 approved questions now and 1 more to add. Hover a cell to see which styles fill it.
      </p>

      <section aria-labelledby="mix" className="flex flex-col gap-2">
        <h3 id="mix" className="font-medium text-sm">
          How the {plan.totalAdd} new questions split across your styles
        </h3>
        <ul className="divide-y rounded-lg border">
          {[...plan.byTemplate]
            .sort((a, b) => b[1] - a[1])
            .map(([id, count]) => {
              const template = byId.get(id);
              if (!template) return null;
              return (
                <li key={id} className="flex flex-wrap items-center gap-x-3 gap-y-1 px-3 py-2 text-sm">
                  <span className="min-w-0 flex-1">{template.name}</span>
                  <TypeBadge label={domain.questionTypes[template.questionType] ?? template.questionType} />
                  <DifficultyBadge difficulty={template.difficulty} />
                  <span className="w-10 text-right font-medium tabular-nums">{count}</span>
                </li>
              );
            })}
        </ul>
      </section>

      {generated ? (
        <div role="status" className="flex items-start gap-3 rounded-lg border bg-muted/30 p-3.5 text-sm">
          <InfoIcon className="mt-0.5 size-4 shrink-0 text-muted-foreground" aria-hidden />
          <div>
            <p className="font-medium">Prototype: nothing was generated.</p>
            <p className="text-muted-foreground">
              In the app this would queue {plan.drafts} drafts in batches. They would appear under Questions as
              “Needs review”, the first {Math.min(12, plan.drafts)} in a short check before the rest are generated.
              Approved questions reach students when you publish a new question set.
            </p>
          </div>
        </div>
      ) : null}
    </div>
  );
}
