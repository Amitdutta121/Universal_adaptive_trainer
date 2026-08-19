"use client";

/**
 * The uploaded curriculum versions, newest first.
 *
 * Status carries a tooltip rather than a column of explanation: `superseded` is
 * the value a professor has to interpret, and it means "a later upload replaced
 * this" — not "this failed".
 */

import { CheckCircle2, MoreHorizontal, Pencil, Trash2 } from "lucide-react";
import Link from "next/link";
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
import type { CurriculumVersionSummary } from "@/lib/api/types";
import { formatTimestamp } from "@/lib/display";
import {
  generatedByLabel,
  STANDING_LABEL,
  STANDING_MEANING,
  STANDING_VARIANT,
  versionStanding,
} from "../curriculum-display";

export function CurriculumVersionsTable({
  versions,
  approvedVersionId,
  activatingVersionId,
  onActivate,
  onEdit,
  onDelete,
}: {
  versions: readonly CurriculumVersionSummary[];
  /** Which row is actually live. Every upload stays `approved`; only one grounds anything. */
  approvedVersionId: number | null | undefined;
  activatingVersionId: number | null;
  onActivate: (version: CurriculumVersionSummary) => void;
  onEdit: (version: CurriculumVersionSummary) => void;
  onDelete: (version: CurriculumVersionSummary) => void;
}) {
  return (
    <Table>
      <TableHeader>
        <TableRow>
          <TableHead className="w-12">#</TableHead>
          <TableHead>Label</TableHead>
          <TableHead>Status</TableHead>
          <TableHead className="text-right">Topics</TableHead>
          <TableHead className="text-right">Subtopics</TableHead>
          <TableHead>Source</TableHead>
          <TableHead>Uploaded</TableHead>
          <TableHead>Approved</TableHead>
          <TableHead className="w-10" />
        </TableRow>
      </TableHeader>
      <TableBody>
        {versions.map((version) => {
          const standing = versionStanding(version, approvedVersionId);
          const canActivate = standing === "replaced";
          const isActivating = activatingVersionId === version.id;
          return (
            <TableRow key={version.id}>
              <TableCell className="text-muted-foreground tabular-nums">{version.id}</TableCell>
              <TableCell className="font-medium">
                <Link href={`/curriculum/versions/${version.id}`} className="hover:underline">
                  {version.label}
                </Link>
              </TableCell>
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
              <TableCell className="text-muted-foreground text-sm">
                {generatedByLabel(version)}
              </TableCell>
              <TableCell className="text-muted-foreground text-sm">
                {formatTimestamp(version.created_at)}
              </TableCell>
              <TableCell className="text-muted-foreground text-sm">
                {version.approved_at ? formatTimestamp(version.approved_at) : "—"}
              </TableCell>
              <TableCell>
                <DropdownMenu>
                  <DropdownMenuTrigger asChild>
                    <Button variant="ghost" size="icon" aria-label={`Actions for ${version.label}`}>
                      <MoreHorizontal />
                    </Button>
                  </DropdownMenuTrigger>
                  <DropdownMenuContent align="end">
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
