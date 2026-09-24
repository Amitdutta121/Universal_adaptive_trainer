"use client";

/**
 * The saved taxonomies, newest first, as the list on the left of the curriculum page.
 *
 * Choosing a row opens a copy of it in the builder beside it. The list is deliberately compact —
 * a name, its size and date, and its standing — because it shares the page with the editor; the
 * full record (source, made-active time, evidence) is one click away on its details page.
 *
 * Status carries a tooltip rather than a column of explanation: `replaced` is the value a
 * professor has to interpret, and it means "a later taxonomy took over" — not "this failed".
 */

import { CheckCircle2, ExternalLink, MoreHorizontal, Pencil, Trash2 } from "lucide-react";
import Link from "next/link";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import { Table, TableBody, TableCell, TableRow } from "@/components/ui/table";
import { Tooltip, TooltipContent, TooltipTrigger } from "@/components/ui/tooltip";
import type { CurriculumVersionSummary } from "@/lib/api/types";
import { formatTimestamp, pluralise } from "@/lib/display";
import { cn } from "@/lib/utils";
import {
  STANDING_LABEL,
  STANDING_MEANING,
  STANDING_VARIANT,
  versionStanding,
} from "../curriculum-display";

export function CurriculumVersionsTable({
  versions,
  approvedVersionId,
  activatingVersionId,
  selectedId,
  openingId,
  onSelect,
  onActivate,
  onEdit,
  onDelete,
}: {
  versions: readonly CurriculumVersionSummary[];
  /** Which row is actually live. Every upload stays `approved`; only one grounds anything. */
  approvedVersionId: number | null | undefined;
  activatingVersionId: number | null;
  /** The taxonomy the builder is showing a copy of. */
  selectedId: number | null;
  /** A row whose tree is still being fetched. */
  openingId: number | null;
  onSelect: (version: CurriculumVersionSummary) => void;
  onActivate: (version: CurriculumVersionSummary) => void;
  onEdit: (version: CurriculumVersionSummary) => void;
  onDelete: (version: CurriculumVersionSummary) => void;
}) {
  return (
    <Table aria-label="Saved taxonomies">
      <TableBody>
        {versions.map((version) => {
          const standing = versionStanding(version, approvedVersionId);
          const canActivate = standing === "replaced";
          const isActivating = activatingVersionId === version.id;
          const selected = selectedId === version.id;
          return (
            <TableRow
              key={version.id}
              data-state={selected ? "selected" : undefined}
              aria-selected={selected}
              tabIndex={0}
              className={cn("cursor-pointer", openingId === version.id && "opacity-60")}
              onClick={() => onSelect(version)}
              onKeyDown={(event) => {
                if (event.target !== event.currentTarget) return;
                if (event.key === "Enter" || event.key === " ") {
                  event.preventDefault();
                  onSelect(version);
                }
              }}
            >
              <TableCell className="whitespace-normal">
                <div className="font-medium">{version.label}</div>
                <div className="text-muted-foreground text-xs">
                  {pluralise(version.topic_count, "topic")} ·{" "}
                  {pluralise(version.subtopic_count, "subtopic")} ·{" "}
                  {formatTimestamp(version.created_at)}
                </div>
              </TableCell>
              <TableCell className="w-px">
                <Tooltip>
                  <TooltipTrigger asChild>
                    <Badge variant={STANDING_VARIANT[standing]}>{STANDING_LABEL[standing]}</Badge>
                  </TooltipTrigger>
                  <TooltipContent>{STANDING_MEANING[standing]}</TooltipContent>
                </Tooltip>
              </TableCell>
              <TableCell className="w-px" onClick={(event) => event.stopPropagation()}>
                <DropdownMenu>
                  <DropdownMenuTrigger asChild>
                    <Button variant="ghost" size="icon" aria-label={`Actions for ${version.label}`}>
                      <MoreHorizontal />
                    </Button>
                  </DropdownMenuTrigger>
                  <DropdownMenuContent align="end">
                    <DropdownMenuItem asChild>
                      <Link href={`/curriculum/versions/${version.id}`}>
                        <ExternalLink />
                        View details
                      </Link>
                    </DropdownMenuItem>
                    <DropdownMenuItem
                      disabled={!canActivate || isActivating}
                      onSelect={() => canActivate && onActivate(version)}
                    >
                      <CheckCircle2 />
                      {isActivating ? "Making active..." : "Make active"}
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
              </TableCell>
            </TableRow>
          );
        })}
      </TableBody>
    </Table>
  );
}
