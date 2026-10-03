"use client";

/**
 * Step 2 · Choose question styles. One style card at a time: two example questions written
 * from it, then "Use this style" or "Skip" (with an optional one-tap reason). The rail keeps
 * score per difficulty, because the adaptive engine needs every difficulty filled.
 */

import { CheckIcon, TriangleAlertIcon, XIcon } from "lucide-react";
import { useEffect, useState } from "react";
import { Button } from "@/components/ui/button";
import { Progress } from "@/components/ui/progress";
import { cn } from "@/lib/utils";
import {
  DIFFICULTIES,
  DIFFICULTY_LABEL,
  type Difficulty,
  type Domain,
  SKIP_REASONS,
  type SkipReason,
  type Template,
} from "../mock-types";
import { approvedByDifficulty, type Decision } from "../plan";
import { DifficultyBadge, TypeBadge } from "./badges";
import { ExampleQuestionView } from "./example-question";

function topicNames(domain: Domain, ids: readonly string[]): string {
  return ids.map((id) => domain.topics.find((topic) => topic.id === id)?.name ?? id).join(", ");
}

function StyleCard({
  domain,
  template,
  position,
  total,
  decision,
  onDecide,
}: {
  domain: Domain;
  template: Template;
  position: number;
  total: number;
  decision: Decision | undefined;
  onDecide(decision: Decision): void;
}) {
  const [askingWhy, setAskingWhy] = useState(false);
  const typeLabel = domain.questionTypes[template.questionType] ?? template.questionType;

  useEffect(() => {
    function onKey(event: KeyboardEvent) {
      const target = event.target as HTMLElement | null;
      if (target && ["INPUT", "TEXTAREA", "SELECT"].includes(target.tagName)) return;
      if (event.metaKey || event.ctrlKey || event.altKey) return;
      if (event.key === "a") onDecide({ verdict: "approved", reason: null });
      if (event.key === "s") setAskingWhy(true);
    }
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [onDecide]);

  return (
    <article aria-labelledby={`style-${template.id}`} className="flex flex-col gap-4">
      <header className="flex flex-col gap-2">
        <p className="text-muted-foreground text-xs tabular-nums">
          Style {position} of {total}
          {decision ? (
            <span className="ml-2">
              · you {decision.verdict === "approved" ? "chose to use it" : "skipped it"}
            </span>
          ) : null}
        </p>
        <h3 id={`style-${template.id}`} className="font-semibold text-base">
          {template.name}
        </h3>
        <p className="text-muted-foreground text-sm">{template.summary}</p>
        <div className="flex flex-wrap items-center gap-2">
          <TypeBadge label={typeLabel} />
          <DifficultyBadge difficulty={template.difficulty} />
        </div>
      </header>

      <dl className="grid gap-x-6 gap-y-1.5 text-sm sm:grid-cols-[auto_1fr]">
        <dt className="text-muted-foreground">Checked by</dt>
        <dd>{template.checkedBy}</dd>
        <dt className="text-muted-foreground">Why suggested</dt>
        <dd>{template.evidence}</dd>
        <dt className="text-muted-foreground">Used for</dt>
        <dd>
          {template.excludeTopics?.length
            ? `Every topic except ${topicNames(domain, template.excludeTopics)}. ${template.excludeReason ?? ""}`
            : "Every topic in your taxonomy"}
        </dd>
      </dl>

      <div className="grid gap-3 md:grid-cols-2">
        <ExampleQuestionView example={template.examples[0]} label="Example 1" />
        <ExampleQuestionView example={template.examples[1]} label="Example 2" />
      </div>

      {askingWhy ? (
        <fieldset className="flex flex-col gap-2 rounded-lg border bg-muted/30 p-3">
          <legend className="float-left mb-2 text-sm">
            Why skip it? <span className="text-muted-foreground">Optional. A reason teaches the generator.</span>
          </legend>
          <div className="flex flex-wrap gap-2">
            {SKIP_REASONS.map((reason: SkipReason) => (
              <Button
                key={reason}
                size="sm"
                variant="outline"
                onClick={() => onDecide({ verdict: "skipped", reason })}
              >
                {reason}
              </Button>
            ))}
            <Button size="sm" variant="ghost" onClick={() => onDecide({ verdict: "skipped", reason: null })}>
              Skip without a reason
            </Button>
          </div>
        </fieldset>
      ) : (
        <div className="flex flex-wrap items-center gap-2">
          <Button variant="outline" onClick={() => setAskingWhy(true)}>
            <XIcon data-icon="inline-start" />
            Skip
          </Button>
          <Button onClick={() => onDecide({ verdict: "approved", reason: null })}>
            <CheckIcon data-icon="inline-start" />
            Use this style
          </Button>
          <span className="ml-auto hidden text-muted-foreground text-xs sm:inline">
            Keys: <kbd className="rounded border px-1 font-mono">A</kbd> use ·{" "}
            <kbd className="rounded border px-1 font-mono">S</kbd> skip
          </span>
        </div>
      )}
    </article>
  );
}

export function StepStyles({
  domain,
  deck,
  cursor,
  onCursor,
  decisions,
  onDecide,
  wishes,
  reserveLeft,
  onAddReserve,
}: {
  domain: Domain;
  deck: readonly Template[];
  cursor: number;
  onCursor(index: number): void;
  decisions: Readonly<Record<string, Decision>>;
  onDecide(templateId: string, decision: Decision): void;
  wishes: ReadonlySet<string>;
  reserveLeft: Readonly<Record<Difficulty, number>>;
  onAddReserve(difficulty: Difficulty): void;
}) {
  const reviewed = deck.filter((template) => decisions[template.id]).length;
  const approved = approvedByDifficulty(deck, decisions);
  const finished = cursor >= deck.length;
  const template = deck[cursor];
  const missing = DIFFICULTIES.filter((d) => approved[d] === 0);

  return (
    <div className="grid gap-6 lg:grid-cols-[minmax(0,1fr)_240px]">
      <div className="min-w-0">
        {wishes.size > 0 ? (
          <p className="mb-4 text-muted-foreground text-xs">
            Suggestions take into account: {[...wishes].join(" · ")}
          </p>
        ) : null}

        {!finished && template ? (
          <StyleCard
            key={template.id}
            domain={domain}
            template={template}
            position={cursor + 1}
            total={deck.length}
            decision={decisions[template.id]}
            onDecide={(decision) => onDecide(template.id, decision)}
          />
        ) : (
          <div className="flex flex-col gap-4">
            <div>
              <h3 className="font-semibold text-base">All {deck.length} styles reviewed</h3>
              <p className="text-muted-foreground text-sm">
                You chose {DIFFICULTIES.reduce((sum, d) => sum + approved[d], 0)}. Click any style in the list
                to change your mind.
              </p>
            </div>
            {missing.map((difficulty) => (
              <div
                key={difficulty}
                role="alert"
                className="flex flex-col gap-3 rounded-lg border border-[var(--warn-solid)]/50 bg-[var(--warn-wash)] p-3.5 text-sm sm:flex-row sm:items-start"
              >
                <TriangleAlertIcon className="mt-0.5 size-4 shrink-0 text-[var(--warn-solid)]" aria-hidden />
                <div className="flex-1">
                  <p className="font-medium">No {DIFFICULTY_LABEL[difficulty].toLowerCase()} style chosen</p>
                  <p className="text-muted-foreground">
                    {difficulty === "hard"
                      ? "Students who have mastered a topic are served hard questions. Without a hard style they get medium ones instead, so practice stops getting harder."
                      : `Students at this mastery level are served ${difficulty} questions. Without a style here they get a different difficulty instead.`}
                  </p>
                </div>
                {reserveLeft[difficulty] > 0 ? (
                  <Button size="sm" variant="outline" onClick={() => onAddReserve(difficulty)}>
                    Show {reserveLeft[difficulty]} more {DIFFICULTY_LABEL[difficulty].toLowerCase()}{" "}
                    {reserveLeft[difficulty] === 1 ? "style" : "styles"}
                  </Button>
                ) : null}
              </div>
            ))}
          </div>
        )}
      </div>

      <aside aria-label="Your choices" className="flex flex-col gap-4 lg:border-l lg:pl-5">
        <div className="flex flex-col gap-1.5">
          <p className="text-muted-foreground text-xs tabular-nums">
            Reviewed {reviewed} of {deck.length}
          </p>
          <Progress value={deck.length ? (reviewed / deck.length) * 100 : 0} />
        </div>

        <div className="flex flex-col gap-1">
          <p className="font-medium text-sm">Chosen per difficulty</p>
          {DIFFICULTIES.map((difficulty) => (
            <div key={difficulty} className="flex items-center justify-between text-sm">
              <DifficultyBadge difficulty={difficulty} />
              <span
                className={cn(
                  "tabular-nums",
                  approved[difficulty] === 0 && reviewed > 0 ? "text-[var(--warn-solid)]" : undefined,
                )}
              >
                {approved[difficulty]}
              </span>
            </div>
          ))}
        </div>

        <ol className="flex flex-col gap-0.5">
          {deck.map((entry, index) => {
            const decision = decisions[entry.id];
            return (
              <li key={entry.id}>
                <button
                  type="button"
                  onClick={() => onCursor(index)}
                  aria-current={index === cursor ? "step" : undefined}
                  className={cn(
                    "flex w-full items-start gap-2 rounded-md px-2 py-1 text-left text-xs outline-none hover:bg-muted focus-visible:ring-3 focus-visible:ring-ring/50",
                    index === cursor && "bg-muted font-medium",
                  )}
                >
                  <span className="mt-0.5 flex size-3.5 shrink-0 items-center justify-center">
                    {decision?.verdict === "approved" ? (
                      <CheckIcon className="size-3.5 text-[var(--ok-solid)]" aria-label="Chosen" />
                    ) : decision?.verdict === "skipped" ? (
                      <XIcon className="size-3.5 text-muted-foreground" aria-label="Skipped" />
                    ) : (
                      <><span aria-hidden className="size-1.5 rounded-full bg-border" /><span className="sr-only">Not reviewed</span></>
                    )}
                  </span>
                  <span className={cn("flex-1", decision?.verdict === "skipped" && "text-muted-foreground")}>
                    {entry.name}
                  </span>
                </button>
              </li>
            );
          })}
        </ol>
      </aside>
    </div>
  );
}
