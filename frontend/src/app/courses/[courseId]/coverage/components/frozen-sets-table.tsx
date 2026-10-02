"use client";

/**
 * Every frozen set, newest first. A row shows `member_count / question_count`
 * only when they differ (a member question was deleted). "Inspect" points the
 * grid above at that snapshot.
 */

import { AlertTriangle } from "lucide-react";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import { Tooltip, TooltipContent, TooltipTrigger } from "@/components/ui/tooltip";
import type { QuestionSetOut } from "@/lib/api/types";
import { formatTimestamp } from "@/lib/display";
import { isDamagedSet } from "../coverage-display";

export function FrozenSetsTable({
  sets,
  activeSetId,
  onInspect,
}: {
  sets: readonly QuestionSetOut[];
  activeSetId: number | null;
  onInspect: (setId: number) => void;
}) {
  return (
    <div className="overflow-x-auto">
      <Table>
        <TableHeader>
          <TableRow>
            <TableHead className="w-12">#</TableHead>
            <TableHead>Label</TableHead>
            <TableHead className="text-right">Questions</TableHead>
            <TableHead>Curriculum</TableHead>
            <TableHead>Frozen</TableHead>
            <TableHead className="w-24" />
          </TableRow>
        </TableHeader>
        <TableBody>
          {sets.map((set) => {
            const damaged = isDamagedSet(set);
            return (
              <TableRow key={set.id} data-active={set.id === activeSetId}>
                <TableCell className="text-muted-foreground tabular-nums">{set.id}</TableCell>
                <TableCell className="font-medium">
                  <div className="flex items-center gap-2">
                    <span>{set.label}</span>
                    {set.notes ? (
                      <Tooltip>
                        <TooltipTrigger asChild>
                          <Badge variant="outline" className="font-normal">
                            notes
                          </Badge>
                        </TooltipTrigger>
                        <TooltipContent className="max-w-xs whitespace-pre-wrap">
                          {set.notes}
                        </TooltipContent>
                      </Tooltip>
                    ) : null}
                  </div>
                </TableCell>
                <TableCell className="text-right tabular-nums">
                  {damaged ? (
                    <Tooltip>
                      <TooltipTrigger asChild>
                        <span className="inline-flex items-center gap-1 text-amber-700 dark:text-amber-400">
                          <AlertTriangle className="size-3.5" />
                          {set.member_count} / {set.question_count}
                        </span>
                      </TooltipTrigger>
                      <TooltipContent>
                        Frozen with {set.question_count}; {set.question_count - set.member_count}{" "}
                        member question(s) have since been deleted.
                      </TooltipContent>
                    </Tooltip>
                  ) : (
                    <span>{set.question_count}</span>
                  )}
                </TableCell>
                <TableCell className="text-muted-foreground text-sm">
                  {set.curriculum_version_id === null
                    ? "curriculum deleted"
                    : `#${set.curriculum_version_id}`}
                </TableCell>
                <TableCell className="text-muted-foreground text-sm">
                  {formatTimestamp(set.created_at)}
                </TableCell>
                <TableCell>
                  <Button
                    variant={set.id === activeSetId ? "secondary" : "ghost"}
                    size="sm"
                    onClick={() => onInspect(set.id)}
                  >
                    {set.id === activeSetId ? "Viewing" : "Inspect"}
                  </Button>
                </TableCell>
              </TableRow>
            );
          })}
        </TableBody>
      </Table>
    </div>
  );
}
