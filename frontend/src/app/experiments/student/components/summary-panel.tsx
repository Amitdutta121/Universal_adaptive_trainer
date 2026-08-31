"use client";

import { CircleCheck, CircleDashed, CircleX, RotateCcw } from "lucide-react";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Progress } from "@/components/ui/progress";
import { cn } from "@/lib/utils";
import { masteryPercent, type Progress as ProgressModel, type ScoreLabel } from "../mock-data";
import type { Attempt } from "../session-types";

const ROW_ICON: Record<ScoreLabel, { icon: typeof CircleCheck; className: string }> = {
  correct: { icon: CircleCheck, className: "text-primary" },
  partial: { icon: CircleDashed, className: "text-amber-600 dark:text-amber-400" },
  incorrect: { icon: CircleX, className: "text-destructive" },
};

export function SummaryPanel({
  learnerName,
  setLabel,
  attempts,
  progress,
  averageScore,
  everythingAnswered,
  reduceMotion,
  onPracticeAgain,
  onStartOver,
}: {
  learnerName: string;
  setLabel: string;
  attempts: Attempt[];
  progress: ProgressModel;
  averageScore: number | null;
  everythingAnswered: boolean;
  reduceMotion: boolean;
  onPracticeAgain: () => void;
  onStartOver: () => void;
}) {
  const indicatorClass = reduceMotion
    ? "[&_[data-slot=progress-indicator]]:transition-none"
    : undefined;
  const strong = attempts.filter((attempt) => attempt.score >= 80).length;

  return (
    <div className="space-y-6">
      <header className="space-y-2">
        <h1 className="font-heading font-semibold text-3xl text-foreground tracking-tight">
          {everythingAnswered ? "You've finished this set" : "Session paused"}
        </h1>
        <p className="text-muted-foreground leading-7">
          {learnerName ? `${learnerName}, you` : "You"} answered {attempts.length}{" "}
          {attempts.length === 1 ? "question" : "questions"} from{" "}
          <strong className="text-foreground">{setLabel}</strong>
          {strong > 0 ? `, ${strong} of them at 80 or above` : ""}.
        </p>
      </header>

      <section className="grid gap-4 sm:grid-cols-3">
        <div className="rounded-xl border border-border bg-card p-4 ring-1 ring-foreground/5">
          <div className="text-muted-foreground text-xs">Answered</div>
          <div className="font-heading font-semibold text-3xl text-foreground tabular-nums">
            {attempts.length}
          </div>
        </div>
        <div className="rounded-xl border border-border bg-card p-4 ring-1 ring-foreground/5">
          <div className="text-muted-foreground text-xs">Average score</div>
          <div className="font-heading font-semibold text-3xl text-foreground tabular-nums">
            {averageScore === null ? "—" : averageScore}
            {averageScore === null ? null : (
              <span className="ml-1 font-sans text-base text-muted-foreground">/100</span>
            )}
          </div>
        </div>
        <div className="rounded-xl border border-border bg-card p-4 ring-1 ring-foreground/5">
          <div className="text-muted-foreground text-xs">Strong answers</div>
          <div className="font-heading font-semibold text-3xl text-foreground tabular-nums">
            {strong}
          </div>
        </div>
      </section>

      <section className="space-y-3 rounded-xl border border-border bg-card p-5 ring-1 ring-foreground/5">
        <h2 className="font-medium text-foreground text-sm">Where your mastery landed</h2>
        {progress.topics.map((topic) => (
          <div key={topic.topicId} className="space-y-1.5">
            <div className="flex items-center justify-between gap-2 text-xs">
              <span className="font-medium text-foreground">{topic.topicName}</span>
              <span className="text-muted-foreground tabular-nums">
                {masteryPercent(topic.pKnown)}%
              </span>
            </div>
            <Progress
              value={masteryPercent(topic.pKnown)}
              className={cn("h-1.5", indicatorClass)}
            />
          </div>
        ))}
      </section>

      {attempts.length > 0 ? (
        <section className="space-y-2 rounded-xl border border-border bg-card p-5 ring-1 ring-foreground/5">
          <h2 className="font-medium text-foreground text-sm">Every question this run</h2>
          <ul className="divide-y divide-border">
            {attempts.map((attempt) => {
              const { icon: Icon, className } = ROW_ICON[attempt.label];
              return (
                <li key={attempt.ordinal} className="flex items-center gap-3 py-2.5 text-sm">
                  <Icon className={cn("size-4 shrink-0", className)} aria-hidden="true" />
                  <span className="min-w-0 flex-1 truncate text-foreground">
                    <span className="text-muted-foreground">Q{attempt.ordinal}</span>{" "}
                    {attempt.subtopicName} — {attempt.questionPrompt}
                  </span>
                  <Badge variant="outline" className="shrink-0 tabular-nums">
                    {attempt.score}/100
                  </Badge>
                </li>
              );
            })}
          </ul>
        </section>
      ) : null}

      <div className="flex flex-col gap-3 sm:flex-row">
        <Button type="button" onClick={onPracticeAgain} className="w-full sm:w-auto">
          <RotateCcw />
          Practise another set
        </Button>
        <Button type="button" variant="outline" onClick={onStartOver} className="w-full sm:w-auto">
          Start over
        </Button>
      </div>
    </div>
  );
}
