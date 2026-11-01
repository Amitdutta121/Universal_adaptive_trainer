"use client";

/**
 * One library style as a row: name, what the student does, question type, difficulty range and
 * how it is checked, with its two example questions behind a disclosure. The caller supplies the
 * decision controls, so the same row serves "use / skip" and "remove".
 */

import { ChevronDown } from "lucide-react";
import type { ReactNode } from "react";
import { Button } from "@/components/ui/button";
import { Collapsible, CollapsibleContent, CollapsibleTrigger } from "@/components/ui/collapsible";
import type { QuestionStyle } from "@/lib/api/types";
import { questionTypeLabel } from "@/lib/question-types/registry";
import { cn } from "@/lib/utils";
import { DifficultyBadge, TypeBadge } from "./badges";
import { ExampleQuestionView } from "./example-question";
import type { ExampleQuestion } from "./types";

/**
 * The fields of a library style the row shows. Structural, because the API client widens the
 * two-example tuple of `QuestionStyle` to a plain array.
 */
export type StyleRowStyle = Pick<
  QuestionStyle,
  "name" | "summary" | "question_type" | "difficulty_range" | "checked_by"
> & { examples: readonly ExampleQuestion[] };

export function StyleRow({
  style,
  controls,
  muted = false,
}: {
  style: StyleRowStyle;
  controls: ReactNode;
  /** Dim the row, e.g. once the professor skipped it. */
  muted?: boolean;
}) {
  return (
    <Collapsible asChild>
      <li className="flex flex-col gap-2 px-3 py-2.5" aria-label={style.name}>
        <div className="flex flex-col gap-2 sm:flex-row sm:items-start sm:gap-4">
          <div className={cn("min-w-0 flex-1", muted && "text-muted-foreground")}>
            <p className="font-medium text-sm">{style.name}</p>
            <p className="text-muted-foreground text-xs">{style.summary}</p>
            <div className="mt-1.5 flex flex-wrap items-center gap-1.5">
              <TypeBadge label={questionTypeLabel(style.question_type)} />
              {style.difficulty_range.map((difficulty) => (
                <DifficultyBadge key={difficulty} difficulty={difficulty} />
              ))}
              <span className="text-muted-foreground text-xs">Checked by: {style.checked_by}</span>
            </div>
          </div>
          <div className="flex shrink-0 items-center gap-1.5">
            <CollapsibleTrigger asChild>
              <Button type="button" variant="ghost" size="sm" className="group/examples">
                Examples
                <ChevronDown
                  data-icon="inline-end"
                  className="transition-transform group-data-[state=open]/examples:rotate-180"
                />
              </Button>
            </CollapsibleTrigger>
            {controls}
          </div>
        </div>
        <CollapsibleContent className="grid gap-3 md:grid-cols-2">
          {style.examples.map((example, index) => (
            <ExampleQuestionView
              key={example.prompt}
              example={example}
              label={`Example ${index + 1}`}
            />
          ))}
        </CollapsibleContent>
      </li>
    </Collapsible>
  );
}
