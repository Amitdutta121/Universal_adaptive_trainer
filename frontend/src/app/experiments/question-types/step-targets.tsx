"use client";

/**
 * Step 3: questions planned per subtopic and difficulty, with each subtopic's resolved styles.
 * A planned level with no style on is flagged; clicking a subtopic jumps back to adjust it.
 */

import { DifficultyBadge } from "@/components/question-setup/badges";
import { Badge } from "@/components/ui/badge";
import {
  Table,
  TableBody,
  TableCell,
  TableFooter,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import { cn } from "@/lib/utils";
import { DIFFICULTIES } from "../question-setup/mock-types";
import {
  type Course,
  covers,
  effective,
  isCustom,
  type SetupState,
  subtopics,
  targetsFor,
} from "./setup-model";

export function TargetsStep({
  course,
  state,
  onAdjust,
}: {
  course: Course;
  state: SetupState;
  onAdjust(subtopicId: string): void;
}) {
  const refs = subtopics(course);
  const byDifficulty = Object.fromEntries(DIFFICULTIES.map((d) => [d, 0])) as Record<
    string,
    number
  >;
  for (const ref of refs) {
    const targets = targetsFor(ref.subtopic);
    for (const d of DIFFICULTIES) byDifficulty[d] += targets[d];
  }
  const total = DIFFICULTIES.reduce((sum, d) => sum + byDifficulty[d], 0);
  const styleById = new Map(course.library.map((style) => [style.id, style]));

  return (
    <div className="min-h-0 flex-1 overflow-y-auto px-6 py-5">
      <h3 className="mb-3 font-semibold text-sm">Target: {total} approved questions</h3>
      <div className="overflow-hidden rounded-lg border">
        <Table>
          <TableHeader>
            <TableRow>
              <TableHead>Subtopic</TableHead>
              <TableHead className="text-right">Styles</TableHead>
              {DIFFICULTIES.map((difficulty) => (
                <TableHead key={difficulty} className="text-right">
                  <span className="inline-flex justify-end">
                    <DifficultyBadge difficulty={difficulty} />
                  </span>
                </TableHead>
              ))}
              <TableHead className="text-right">Total</TableHead>
            </TableRow>
          </TableHeader>
          {course.topics.map((topic) => (
            <TableBody key={topic.id}>
              <TableRow className="bg-muted/40 hover:bg-muted/40">
                <TableCell colSpan={DIFFICULTIES.length + 3} className="font-medium text-xs">
                  {topic.name}
                </TableCell>
              </TableRow>
              {refs
                .filter((ref) => ref.topicId === topic.id)
                .map((ref) => {
                  const on = effective(state, course, ref);
                  const targets = targetsFor(ref.subtopic);
                  return (
                    <TableRow key={ref.subtopic.id}>
                      <TableCell className="pl-5">
                        <button
                          type="button"
                          onClick={() => onAdjust(ref.subtopic.id)}
                          className="text-left underline-offset-2 hover:underline"
                        >
                          {ref.subtopic.name}
                        </button>
                        {isCustom(state, ref.subtopic.id) ? (
                          <Badge variant="outline" className="ml-2 h-5 px-1.5 text-[11px]">
                            Custom
                          </Badge>
                        ) : null}
                      </TableCell>
                      <TableCell className="text-right tabular-nums">{on.size}</TableCell>
                      {DIFFICULTIES.map((difficulty) => {
                        const gap =
                          targets[difficulty] > 0 &&
                          ![...on].some((id) => {
                            const style = styleById.get(id);
                            return style ? covers(style, difficulty) : false;
                          });
                        return (
                          <TableCell
                            key={difficulty}
                            className={cn(
                              "text-right tabular-nums",
                              gap && "bg-[var(--warn-wash)] font-medium text-[var(--warn-solid)]",
                            )}
                            title={gap ? "No style on at this level" : undefined}
                          >
                            {targets[difficulty] || (
                              <span className="text-muted-foreground">–</span>
                            )}
                            {gap ? " · no style" : null}
                          </TableCell>
                        );
                      })}
                      <TableCell className="text-right font-medium tabular-nums">
                        {DIFFICULTIES.reduce((sum, d) => sum + targets[d], 0)}
                      </TableCell>
                    </TableRow>
                  );
                })}
            </TableBody>
          ))}
          <TableFooter>
            <TableRow>
              <TableCell colSpan={2}>Total</TableCell>
              {DIFFICULTIES.map((difficulty) => (
                <TableCell key={difficulty} className="text-right tabular-nums">
                  {byDifficulty[difficulty]}
                </TableCell>
              ))}
              <TableCell className="text-right tabular-nums">{total}</TableCell>
            </TableRow>
          </TableFooter>
        </Table>
      </div>
    </div>
  );
}
