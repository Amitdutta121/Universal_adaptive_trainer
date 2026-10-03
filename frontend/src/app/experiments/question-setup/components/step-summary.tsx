"use client";

/**
 * Step 3 · Your styles. The deliverable of the review: the templates the professor chose,
 * grouped by difficulty, plus the rules the generator takes from their skips.
 */

import { Button } from "@/components/ui/button";
import { DIFFICULTIES, DIFFICULTY_LABEL, type Domain, type Template } from "../mock-types";
import { type Decision, rulesFromSkips } from "../plan";
import { DifficultyBadge, TypeBadge } from "./badges";

export function StepSummary({
  domain,
  deck,
  decisions,
  onDecide,
}: {
  domain: Domain;
  deck: readonly Template[];
  decisions: Readonly<Record<string, Decision>>;
  onDecide(templateId: string, decision: Decision): void;
}) {
  const chosen = deck.filter((template) => decisions[template.id]?.verdict === "approved");
  const skipped = deck.filter((template) => decisions[template.id]?.verdict === "skipped");
  const rules = rulesFromSkips(deck, decisions, domain.questionTypes);

  return (
    <div className="flex flex-col gap-6">
      <section aria-labelledby="chosen" className="flex flex-col gap-3">
        <h3 id="chosen" className="font-medium text-sm">
          {chosen.length} {chosen.length === 1 ? "style" : "styles"} the generator will use
        </h3>
        {DIFFICULTIES.map((difficulty) => {
          const rows = chosen.filter((template) => template.difficulty === difficulty);
          return (
            <div key={difficulty} className="flex flex-col gap-1.5">
              <div className="flex items-center gap-2">
                <DifficultyBadge difficulty={difficulty} />
                <span className="text-muted-foreground text-xs">
                  {rows.length === 0 ? `No ${DIFFICULTY_LABEL[difficulty].toLowerCase()} style yet` : null}
                </span>
              </div>
              {rows.length > 0 ? (
                <ul className="divide-y rounded-lg border">
                  {rows.map((template) => (
                    <li key={template.id} className="flex flex-col gap-1 px-3 py-2.5 sm:flex-row sm:items-center sm:gap-4">
                      <div className="min-w-0 flex-1">
                        <p className="text-sm">{template.name}</p>
                        <p className="text-muted-foreground text-xs">{template.checkedBy}</p>
                      </div>
                      <TypeBadge label={domain.questionTypes[template.questionType] ?? template.questionType} />
                      <Button
                        size="sm"
                        variant="ghost"
                        onClick={() => onDecide(template.id, { verdict: "skipped", reason: null })}
                      >
                        Remove
                      </Button>
                    </li>
                  ))}
                </ul>
              ) : null}
            </div>
          );
        })}
      </section>

      <section aria-labelledby="rules" className="flex flex-col gap-2 border-t pt-5">
        <h3 id="rules" className="font-medium text-sm">
          Rules taken from your skips
        </h3>
        {rules.length > 0 ? (
          <>
            <ul className="flex list-disc flex-col gap-1 pl-5 text-sm">
              {rules.map((rule) => (
                <li key={rule}>{rule}</li>
              ))}
            </ul>
            <p className="text-muted-foreground text-xs">
              These join the generator's instructions for each question type, next to the rules learned from
              your later reviews. You can edit or delete any of them.
            </p>
          </>
        ) : (
          <p className="text-muted-foreground text-sm">
            None yet. Skips with a reason become rules; skips without one only drop the style.
          </p>
        )}
      </section>

      {skipped.length > 0 ? (
        <section aria-labelledby="skipped" className="flex flex-col gap-2 border-t pt-5">
          <h3 id="skipped" className="font-medium text-sm">
            Skipped
          </h3>
          <ul className="flex flex-col gap-1">
            {skipped.map((template) => (
              <li key={template.id} className="flex flex-wrap items-center gap-x-3 gap-y-1 text-sm">
                <span className="text-muted-foreground">{template.name}</span>
                {decisions[template.id]?.reason ? (
                  <span className="text-muted-foreground text-xs">· {decisions[template.id]?.reason}</span>
                ) : null}
                <Button
                  size="sm"
                  variant="ghost"
                  className="ml-auto"
                  onClick={() => onDecide(template.id, { verdict: "approved", reason: null })}
                >
                  Use instead
                </Button>
              </li>
            ))}
          </ul>
        </section>
      ) : null}
    </div>
  );
}
