"use client";

/**
 * The saved taxonomies, newest first: the main view of the curriculum page.
 *
 * The table only shows data. Choosing a row, or its Preview button, opens the taxonomy in the
 * builder modal (as a copy: saving there creates a new version). The `…` menu keeps what is done
 * to a taxonomy as a whole: its details page, making it active, renaming and deleting.
 *
 * Status carries a tooltip rather than a column of explanation: `replaced` is the value a
 * professor has to interpret, and it means "a later taxonomy took over" — not "this failed".
 */

import { ExternalLink, Eye, MoreHorizontal, Pencil, Trash2 } from "lucide-react";
import { CourseLink } from "@/components/course-link";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import { Tooltip, TooltipContent, TooltipTrigger } from "@/components/ui/tooltip";
import type { CurriculumVersionSummary, StyleTrust } from "@/lib/api/types";
import { formatTimestamp } from "@/lib/display";
import { cn } from "@/lib/utils";
import {
  alignmentsForVersion,
  generatedByLabel,
  STANDING_LABEL,
  STANDING_MEANING,
  STANDING_VARIANT,
  versionStanding,
} from "../curriculum-display";

function JudgeFigure({ label, value }: { label: string; value: string }) {
  return (
    <div>
      <div className="review-eyebrow">{label}</div>
      <div className="mt-0.5 font-semibold text-sm tabular-nums leading-none tracking-tight">
        {value}
      </div>
    </div>
  );
}

export function CurriculumVersionsTable({
  versions,
  styles,
  approvedVersionId,
  openingId,
  onOpen,
  onEdit,
  onDelete,
}: {
  versions: readonly CurriculumVersionSummary[];
  /** Style windows from `GET /api/judge-prompts/stats`, used to fill Judges. */
  styles?: readonly StyleTrust[];
  /** Which row is chosen in the header's taxonomy selector. */
  approvedVersionId: number | null | undefined;
  /** A row whose tree is still being fetched for the builder. */
  openingId: number | null;
  onOpen: (version: CurriculumVersionSummary) => void;
  onEdit: (version: CurriculumVersionSummary) => void;
  onDelete: (version: CurriculumVersionSummary) => void;
}) {
  return (
    <Table aria-label="Saved taxonomies">
      <TableHeader>
        <TableRow>
          <TableHead className="w-12">#</TableHead>
          <TableHead>Name</TableHead>
          <TableHead>Status</TableHead>
          <TableHead className="text-right">Topics</TableHead>
          <TableHead className="text-right">Subtopics</TableHead>
          <TableHead>Judges</TableHead>
          <TableHead>Source</TableHead>
          <TableHead>Created</TableHead>
          <TableHead>Last selected</TableHead>
          <TableHead className="w-40" />
        </TableRow>
      </TableHeader>
      <TableBody>
        {versions.map((version) => {
          const standing = versionStanding(version, approvedVersionId);
          const judges = alignmentsForVersion(styles, version.id);
          return (
            <TableRow
              key={version.id}
              tabIndex={0}
              className={cn("cursor-pointer", openingId === version.id && "opacity-60")}
              onClick={() => onOpen(version)}
              onKeyDown={(event) => {
                if (event.target !== event.currentTarget) return;
                if (event.key === "Enter" || event.key === " ") {
                  event.preventDefault();
                  onOpen(version);
                }
              }}
            >
              <TableCell className="text-muted-foreground tabular-nums">{version.id}</TableCell>
              <TableCell className="font-medium">{version.label}</TableCell>
              <TableCell>
                <Tooltip>
                  <TooltipTrigger asChild>
                    <Badge variant={STANDING_VARIANT[standing]}>{STANDING_LABEL[standing]}</Badge>
                  </TooltipTrigger>
                  <TooltipContent>{STANDING_MEANING[standing]}</TooltipContent>
                </Tooltip>
              </TableCell>
              <TableCell className="text-right tabular-nums">{version.topic_count}</TableCell>
              <TableCell className="text-right tabular-nums">{version.subtopic_count}</TableCell>
              <TableCell>
                <div className="flex items-start">
                  <div className="pr-5">
                    <JudgeFigure label="Difficulty" value={judges.difficulty} />
                  </div>
                  <div className="border-border border-l pl-5">
                    <JudgeFigure label="Topic" value={judges.subtopic} />
                  </div>
                </div>
              </TableCell>
              <TableCell className="text-muted-foreground text-sm">
                {generatedByLabel(version)}
              </TableCell>
              <TableCell className="text-muted-foreground text-sm">
                {formatTimestamp(version.created_at)}
              </TableCell>
              <TableCell className="text-muted-foreground text-sm">
                {version.approved_at ? formatTimestamp(version.approved_at) : "—"}
              </TableCell>
              <TableCell onClick={(event) => event.stopPropagation()}>
                <div className="flex items-center justify-end gap-1">
                  <Button
                    variant="outline"
                    size="sm"
                    aria-label={`Preview ${version.label}`}
                    onClick={() => onOpen(version)}
                  >
                    <Eye />
                    Preview
                  </Button>
                  <DropdownMenu>
                    <DropdownMenuTrigger asChild>
                      <Button
                        variant="ghost"
                        size="icon"
                        aria-label={`Actions for ${version.label}`}
                      >
                        <MoreHorizontal />
                      </Button>
                    </DropdownMenuTrigger>
                    <DropdownMenuContent align="end">
                      <DropdownMenuItem asChild>
                        <CourseLink href={`/curriculum/versions/${version.id}`}>
                          <ExternalLink />
                          View details
                        </CourseLink>
                      </DropdownMenuItem>
                      <DropdownMenuItem onSelect={() => onEdit(version)}>
                        <Pencil />
                        Rename
                      </DropdownMenuItem>
                      <DropdownMenuItem variant="destructive" onSelect={() => onDelete(version)}>
                        <Trash2 />
                        Delete
                      </DropdownMenuItem>
                    </DropdownMenuContent>
                  </DropdownMenu>
                </div>
              </TableCell>
            </TableRow>
          );
        })}
      </TableBody>
    </Table>
  );
}
