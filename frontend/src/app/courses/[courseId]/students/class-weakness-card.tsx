"use client";

/**
 * Class weakness: a heatmap of the course's subtopics, darker where the class is weaker, from
 * `GET /api/students/class-summary`. Clicking a cell lists the students with weakness recorded
 * there. The Roster and the course Dashboard both show it; on the Roster a student row selects
 * that learner (`onSelectStudent`), elsewhere the rows only inform.
 */

import { ArrowRight, GraduationCap } from "lucide-react";
import type { Route } from "next";
import Link from "next/link";
import { useState } from "react";
import { EmptyState, QueryError, TableSkeleton } from "@/components/query-state";
import { Badge } from "@/components/ui/badge";
import {
  Card,
  CardContent,
  CardDescription,
  CardFooter,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import {
  Tooltip as HoverTooltip,
  TooltipContent,
  TooltipProvider,
  TooltipTrigger,
} from "@/components/ui/tooltip";
import { useClassSummary } from "@/lib/api/queries";

function weaknessColor(value: number) {
  const clamped = Math.max(0, Math.min(1, value));
  if (clamped >= 0.8) return "bg-rose-600";
  if (clamped >= 0.6) return "bg-rose-500";
  if (clamped >= 0.4) return "bg-amber-500";
  if (clamped >= 0.2) return "bg-lime-500";
  return "bg-emerald-500";
}

export function ClassWeaknessCard({
  curriculumVersionId = null,
  onSelectStudent,
  showAffected = true,
  compact = false,
  seeMoreHref,
}: {
  /** One taxonomy's students; null for every student in the course. */
  curriculumVersionId?: number | null;
  onSelectStudent?: (studentId: number) => void;
  /** Off: cells only show their tooltip, with no click-through to the affected students. */
  showAffected?: boolean;
  /** A small card for the Dashboard: fixed small cells, a one-line header. */
  compact?: boolean;
  /** Where "See more" leads (the Roster's full heatmap); no link when unset. */
  seeMoreHref?: Route;
}) {
  const summary = useClassSummary(curriculumVersionId);
  const [selectedSubtopicId, setSelectedSubtopicId] = useState<number | null>(null);
  const weaknessCells = summary.data?.weakness_cells ?? [];
  const selectedCell =
    weaknessCells.find((cell) => cell.subtopic_id === selectedSubtopicId) ?? null;
  const affectedStudents = selectedCell?.affected ?? [];

  return (
    <Card className={compact ? "h-full gap-3 border-border/70 py-4" : "border-border/70"}>
      {compact ? (
        <CardHeader className="flex flex-row items-center justify-between gap-3">
          <CardTitle className="flex items-center gap-2 text-base">
            <GraduationCap className="size-4 text-muted-foreground" />
            Class weakness
          </CardTitle>
          <Badge variant="outline">{weaknessCells.length} subtopics</Badge>
        </CardHeader>
      ) : (
        <CardHeader className="gap-3">
          <div className="flex items-center gap-2 text-muted-foreground text-xs uppercase tracking-[0.18em]">
            <GraduationCap className="size-3.5" />
            Class weakness
          </div>
          <div className="flex items-center justify-between gap-3">
            <CardTitle className="text-xl">Class weakness</CardTitle>
            <Badge variant="outline">{weaknessCells.length} subtopics</Badge>
          </div>
          <CardDescription>
            Darker cells mark weaker areas across the class. Hover a cell to see the topic and
            subtopic.
          </CardDescription>
        </CardHeader>
      )}
      <CardContent>
        {summary.isPending ? (
          <TableSkeleton rows={3} />
        ) : summary.isError ? (
          <QueryError error={summary.error} />
        ) : weaknessCells.length === 0 ? (
          <EmptyState
            title="No weakness data yet"
            hint="The heatmap appears after students answer enough questions to build weakness data."
          />
        ) : (
          <div className={compact ? "space-y-2" : "space-y-3"}>
            <TooltipProvider>
              <div
                className={
                  compact
                    ? "flex flex-wrap gap-1 [&>*]:size-7"
                    : "grid grid-cols-8 gap-1 sm:grid-cols-10 xl:grid-cols-12"
                }
              >
                {weaknessCells.map((cell) => (
                  <HoverTooltip key={cell.subtopic_id}>
                    <TooltipTrigger asChild>
                      {showAffected ? (
                        <button
                          type="button"
                          onClick={() => setSelectedSubtopicId(cell.subtopic_id)}
                          className={`aspect-square rounded-md transition-transform hover:scale-105 ${
                            weaknessColor(cell.average_weakness)
                          } ${
                            cell.subtopic_id === selectedSubtopicId
                              ? "ring-2 ring-foreground/60 ring-offset-1"
                              : ""
                          }`}
                          aria-label={`${cell.topic_name} ${cell.subtopic_name}`}
                        />
                      ) : (
                        // Not a control here: its label carries what the tooltip shows.
                        <div
                          role="img"
                          className={`aspect-square rounded-md ${weaknessColor(cell.average_weakness)}`}
                          aria-label={`${cell.topic_name} ${cell.subtopic_name}: weakness ${cell.average_weakness.toFixed(2)}`}
                        />
                      )}
                    </TooltipTrigger>
                    <TooltipContent side="top" sideOffset={8} className="max-w-[220px]">
                      <div className="space-y-1">
                        <div className="font-medium text-background">{cell.subtopic_name}</div>
                        <div className="text-background/80">{cell.topic_name}</div>
                        <div className="text-background/80">
                          Weakness {cell.average_weakness.toFixed(2)} · {cell.student_count}{" "}
                          student(s)
                        </div>
                        {showAffected ? (
                          <div className="text-background/80">Click to view affected students</div>
                        ) : null}
                      </div>
                    </TooltipContent>
                  </HoverTooltip>
                ))}
              </div>
            </TooltipProvider>
            <div className="flex items-center gap-2 text-[11px] text-muted-foreground">
              <span>Lower</span>
              <div className="flex gap-1">
                <span className="h-2.5 w-2.5 rounded-sm bg-emerald-500" />
                <span className="h-2.5 w-2.5 rounded-sm bg-lime-500" />
                <span className="h-2.5 w-2.5 rounded-sm bg-amber-500" />
                <span className="h-2.5 w-2.5 rounded-sm bg-rose-500" />
                <span className="h-2.5 w-2.5 rounded-sm bg-rose-600" />
              </div>
              <span>Higher weakness</span>
            </div>
            {!showAffected ? null : selectedCell ? (
              <div className="rounded-xl border border-border/70 bg-muted/20 p-3">
                <div>
                  <div className="font-medium">{selectedCell.subtopic_name}</div>
                  <div className="text-muted-foreground text-sm">
                    {selectedCell.topic_name} · weakness {selectedCell.average_weakness.toFixed(2)}{" "}
                    · {selectedCell.student_count} student(s)
                  </div>
                </div>
                <div className="mt-3 space-y-2">
                  {affectedStudents.slice(0, 6).map((student) => {
                    const line = (
                      <>
                        <span className="font-medium">{student.name}</span>
                        <span className="text-muted-foreground text-sm">
                          weakness {student.weakness.toFixed(2)} · {student.answered} answered
                        </span>
                      </>
                    );
                    const rowClass =
                      "flex w-full items-center justify-between rounded-lg border border-border/60 bg-background px-3 py-2 text-left";
                    return onSelectStudent ? (
                      <button
                        key={student.id}
                        type="button"
                        onClick={() => onSelectStudent(student.id)}
                        className={`${rowClass} hover:bg-muted/30`}
                      >
                        {line}
                      </button>
                    ) : (
                      <div key={student.id} className={rowClass}>
                        {line}
                      </div>
                    );
                  })}
                </div>
              </div>
            ) : (
              <div className="rounded-xl border border-border/70 border-dashed px-3 py-2 text-muted-foreground text-sm">
                Click a heatmap cell to see the students with weakness recorded in that area.
              </div>
            )}
          </div>
        )}
      </CardContent>
      {seeMoreHref ? (
        // Pinned to the card's foot, in line with the other dashboard cards' bottoms.
        <CardFooter className="mt-auto">
          <Link
            href={seeMoreHref}
            className="inline-flex items-center gap-1 font-medium text-primary text-sm hover:underline"
          >
            See more
            <ArrowRight className="size-3.5" />
          </Link>
        </CardFooter>
      ) : null}
    </Card>
  );
}
