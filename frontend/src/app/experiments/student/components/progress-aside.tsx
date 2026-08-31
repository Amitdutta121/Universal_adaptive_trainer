"use client";

import { Badge } from "@/components/ui/badge";
import { Progress } from "@/components/ui/progress";
import { cn } from "@/lib/utils";
import { masteryPercent, type Progress as ProgressModel, weaknessPercent } from "../mock-data";

export function ProgressAside({
  progress,
  answered,
  averageScore,
  reduceMotion,
}: {
  progress: ProgressModel;
  answered: number;
  averageScore: number | null;
  reduceMotion: boolean;
}) {
  const focusAreas = [...progress.subtopics]
    .sort((left, right) => right.weakness - left.weakness)
    .slice(0, 4);
  const indicatorClass = reduceMotion
    ? "[&_[data-slot=progress-indicator]]:transition-none"
    : undefined;

  return (
    <aside
      aria-label="Your progress"
      className="space-y-5 rounded-xl border border-border bg-card p-5 ring-1 ring-foreground/5"
    >
      <div className="flex gap-6">
        <div>
          <div className="text-muted-foreground text-xs">Answered</div>
          <div className="font-heading font-semibold text-2xl text-foreground tabular-nums">
            {answered}
          </div>
        </div>
        <div>
          <div className="text-muted-foreground text-xs">Average score</div>
          <div className="font-heading font-semibold text-2xl text-foreground tabular-nums">
            {averageScore === null ? "—" : `${averageScore}`}
            {averageScore === null ? null : (
              <span className="ml-1 font-sans text-muted-foreground text-sm">/100</span>
            )}
          </div>
        </div>
      </div>

      <div className="space-y-3 border-border border-t pt-4">
        <h3 className="font-medium text-foreground text-sm">Topic mastery</h3>
        {progress.topics.map((topic) => (
          <div key={topic.topicId} className="space-y-1.5">
            <div className="flex items-center justify-between gap-2 text-xs">
              <span className="font-medium text-foreground">{topic.topicName}</span>
              <Badge
                variant={topic.band === "high" ? "secondary" : "outline"}
                className="capitalize"
              >
                {topic.band}
              </Badge>
            </div>
            <Progress
              value={masteryPercent(topic.pKnown)}
              className={cn("h-1.5", indicatorClass)}
            />
          </div>
        ))}
      </div>

      <div className="space-y-3 border-border border-t pt-4">
        <div>
          <h3 className="font-medium text-foreground text-sm">Focus areas</h3>
          <p className="text-muted-foreground text-xs">
            What the adaptive engine is weighting most heavily for you right now.
          </p>
        </div>
        {focusAreas.map((subtopic) => (
          <div key={subtopic.subtopicId} className="space-y-1.5">
            <div className="text-xs">
              <span className="font-medium text-foreground">{subtopic.subtopicName}</span>
              <span className="text-muted-foreground"> · {subtopic.topicName}</span>
            </div>
            <Progress
              value={weaknessPercent(subtopic.weakness)}
              className={cn("h-1.5", indicatorClass)}
            />
          </div>
        ))}
      </div>
    </aside>
  );
}
