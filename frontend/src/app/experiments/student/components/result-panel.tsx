"use client";

import { ArrowRight, CircleCheck, CircleDashed, CircleX, Lightbulb } from "lucide-react";
import { forwardRef } from "react";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Progress } from "@/components/ui/progress";
import { cn } from "@/lib/utils";
import { masteryPercent, type Question, type ScoreLabel, scoreLabelText } from "../mock-data";
import type { LastResult } from "../session-types";
import { AnswerReview } from "./answer-review";

const TONE: Record<
  ScoreLabel,
  {
    icon: typeof CircleCheck;
    border: string;
    text: string;
    badge: "secondary" | "outline" | "destructive";
  }
> = {
  correct: {
    icon: CircleCheck,
    border: "border-primary/40",
    text: "text-primary",
    badge: "secondary",
  },
  partial: {
    icon: CircleDashed,
    border: "border-amber-500/40",
    text: "text-amber-700 dark:text-amber-300",
    badge: "outline",
  },
  incorrect: {
    icon: CircleX,
    border: "border-destructive/40",
    text: "text-destructive",
    badge: "destructive",
  },
};

export const ResultPanel = forwardRef<
  HTMLDivElement,
  {
    result: LastResult;
    question: Question;
    onNext: () => void;
    reduceMotion: boolean;
    isLastInSet: boolean;
  }
>(function ResultPanel({ result, question, onNext, reduceMotion, isLastInSet }, ref) {
  const tone = TONE[result.label];
  const Icon = tone.icon;
  const beforePct = masteryPercent(result.topicBefore);
  const afterPct = masteryPercent(result.topicAfter);
  const delta = afterPct - beforePct;

  return (
    <section
      aria-labelledby="result-heading"
      className={cn(
        "space-y-5 rounded-xl border bg-card p-5 ring-1 ring-foreground/5 sm:p-6",
        tone.border,
      )}
    >
      <div
        ref={ref}
        tabIndex={-1}
        className="flex flex-col gap-4 rounded-lg outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2 focus-visible:ring-offset-background sm:flex-row sm:items-start sm:justify-between"
      >
        <div className="space-y-3">
          <div className="flex flex-wrap items-center gap-2.5">
            <Icon className={cn("size-6", tone.text)} aria-hidden="true" />
            <h2
              id="result-heading"
              className="font-heading font-semibold text-foreground text-xl tracking-tight"
            >
              {scoreLabelText(result.label)}
            </h2>
            <Badge variant={tone.badge}>{result.score} / 100</Badge>
            {result.totalChecks ? (
              <span className="text-muted-foreground text-sm">
                {result.passedChecks} of {result.totalChecks} lines in place
              </span>
            ) : null}
          </div>
          <p className="max-w-prose text-foreground text-sm leading-7">{result.detail}</p>
        </div>
        <Button type="button" onClick={onNext} className="w-full shrink-0 sm:w-auto">
          <ArrowRight />
          {isLastInSet ? "See summary" : "Next question"}
        </Button>
      </div>

      <div className="space-y-2 border-border border-t pt-4">
        <div className="flex items-center justify-between gap-3 text-sm">
          <span className="font-medium text-foreground">{result.topicName} mastery</span>
          <span className="text-muted-foreground">
            {beforePct}% → <strong className="text-foreground">{afterPct}%</strong>
            <span
              className={cn("ml-2", delta > 0 && "text-primary", delta < 0 && "text-destructive")}
            >
              {delta > 0 ? `+${delta}` : delta}
            </span>
          </span>
        </div>
        <Progress
          value={afterPct}
          className={cn(
            "h-2",
            reduceMotion && "[&_[data-slot=progress-indicator]]:transition-none",
          )}
        />
      </div>

      <div className="space-y-3 border-border border-t pt-4">
        <h3 className="flex items-center gap-2 font-medium text-foreground text-sm">
          <Lightbulb className="size-4 text-primary" aria-hidden="true" />
          What was correct
        </h3>
        <AnswerReview question={question} answer={result.answer} />
      </div>
    </section>
  );
});
