"use client";

import { Link as LinkIcon } from "lucide-react";
import type { Route } from "next";
import Link from "next/link";
import { useEffect, useState } from "react";
import { toast } from "sonner";
import { CopyButton } from "@/components/copy-button";
import { PageHeader } from "@/components/page-header";
import { EmptyState, QueryError, TableSkeleton } from "@/components/query-state";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import {
  useApprovedCurriculum,
  useQuestionSets,
  useSyncTaxonomyClassroom,
  useTaxonomyClassroom,
  useTaxonomyLinks,
} from "@/lib/api/queries";
import { SECTIONS_BY_KEY } from "@/lib/navigation";

function formatDate(value: string | null, withTime = false) {
  if (!value) return "Open";
  return new Intl.DateTimeFormat(undefined, {
    dateStyle: "medium",
    ...(withTime ? { timeStyle: "short" } : {}),
  }).format(new Date(value));
}

export function StudentsScreen() {
  const section = SECTIONS_BY_KEY.classrooms;
  const allQuestionSets = useQuestionSets();
  // Everything here is about the taxonomy chosen in the header: its own classroom link,
  // and the snapshots frozen from it. Any taxonomy can have a link; it need not be "live".
  const selectedTaxonomy = useApprovedCurriculum();
  const taxonomyId = selectedTaxonomy.data?.version.id ?? null;
  const classroom = useTaxonomyClassroom(taxonomyId);
  const syncLink = useSyncTaxonomyClassroom();
  const taxonomyLinks = useTaxonomyLinks();
  const questionSets = {
    ...allQuestionSets,
    data: allQuestionSets.data
      ? {
          ...allQuestionSets.data,
          sets: allQuestionSets.data.sets.filter(
            (entry) => entry.curriculum_version_id === taxonomyId,
          ),
        }
      : undefined,
  };

  const [origin, setOrigin] = useState("");

  useEffect(() => {
    setOrigin(window.location.origin);
  }, []);

  const taxonomyLink = origin && taxonomyId ? `${origin}/students/join?taxonomy=${taxonomyId}` : "";

  /** Create or update one taxonomy's link: the selected one, or any row of the list. */
  async function updateClassroomLink(versionId: number | null = taxonomyId) {
    if (versionId === null) return;
    try {
      const synced = await syncLink.mutateAsync(versionId);
      toast.success(
        `Classroom link now serves snapshot #${synced.id} (${synced.question_count} questions).`,
      );
    } catch {
      // Shown in the card with the backend's own wording.
    }
  }

  return (
    <>
      <PageHeader
        title={section.label}
        summary="Generate a joinable adaptive-training classroom"
        actions={
          questionSets.data ? (
            <Badge variant="outline" className="h-7 rounded-full px-3 font-mono tracking-[0.08em]">
              {questionSets.data.sets.length} frozen sets
            </Badge>
          ) : null
        }
      />

      <div className="space-y-4">
        {taxonomyId !== null ? (
          <Card className="border-border/70">
            <CardHeader className="gap-2">
              <div className="flex items-center gap-2 text-muted-foreground text-xs uppercase tracking-[0.18em]">
                <LinkIcon className="size-3.5" />
                Classroom link
              </div>
              <CardTitle className="text-xl">{selectedTaxonomy.data?.version.label}</CardTitle>
            </CardHeader>
            <CardContent className="space-y-3">
              {classroom.data ? (
                <div className="flex flex-col gap-2 md:flex-row">
                    <Input
                      aria-label="Classroom link"
                      value={taxonomyLink}
                      readOnly
                      className="font-mono text-xs"
                    />
                    <div className="flex gap-2">
                      <CopyButton text={taxonomyLink} label="Copy link" copiedLabel="Copied" />
                      <Button asChild variant="secondary" size="sm">
                        <Link href={`/students/join?taxonomy=${taxonomyId}` as Route}>
                          Open lobby
                        </Link>
                      </Button>
                    </div>
                  </div>
              ) : classroom.isPending ? (
                <TableSkeleton rows={1} />
              ) : (
                <p className="text-muted-foreground text-sm">
                  No classroom link yet. Creating it freezes this taxonomy's approved questions.
                </p>
              )}
              {syncLink.error ? <QueryError error={syncLink.error} /> : null}
              {classroom.data || classroom.isPending ? null : (
                <Button
                  type="button"
                  size="sm"
                  disabled={syncLink.isPending}
                  onClick={() => void updateClassroomLink()}
                >
                  {syncLink.isPending ? "Freezing…" : "Create classroom link"}
                </Button>
              )}

              <div className="space-y-2 border-border/60 border-t pt-4">
                <div className="font-medium text-sm">Every taxonomy in this course</div>
                {taxonomyLinks.isPending ? <TableSkeleton rows={3} /> : null}
                {taxonomyLinks.isError ? <QueryError error={taxonomyLinks.error} /> : null}
                {taxonomyLinks.data ? (
                  <div className="rounded-xl border border-border/70">
                    <Table aria-label="Classroom links by taxonomy">
                      <TableHeader>
                        <TableRow>
                          <TableHead>Taxonomy</TableHead>
                          <TableHead>Classroom link</TableHead>
                          <TableHead>Snapshot</TableHead>
                          <TableHead className="text-right">Questions</TableHead>
                          <TableHead className="w-28" />
                        </TableRow>
                      </TableHeader>
                      <TableBody>
                        {taxonomyLinks.data.links.map((row) => {
                          const id = row.curriculum_version_id;
                          const link = origin ? `${origin}/students/join?taxonomy=${id}` : "";
                          const busy = syncLink.isPending && syncLink.variables === id;
                          return (
                            <TableRow
                              key={id}
                              data-selected={id === taxonomyId || undefined}
                              className="data-[selected]:bg-muted/40"
                            >
                              <TableCell className="max-w-[18rem]">
                                <div className="truncate font-medium" title={row.label}>
                                  {row.label}
                                </div>
                                <div className="text-muted-foreground text-xs">
                                  v{id}
                                  {id === taxonomyId ? " · selected" : ""}
                                </div>
                              </TableCell>
                              <TableCell>
                                {row.classroom ? (
                                  <div className="flex items-center gap-2">
                                    <span className="font-mono text-xs">…/join?taxonomy={id}</span>
                                    <CopyButton text={link} label="Copy" copiedLabel="Copied" />
                                  </div>
                                ) : (
                                  <span className="text-muted-foreground text-sm">No link yet</span>
                                )}
                              </TableCell>
                              <TableCell className="text-sm">
                                {row.classroom
                                  ? `#${row.classroom.id} · ${formatDate(row.classroom.created_at)}`
                                  : "—"}
                              </TableCell>
                              <TableCell className="text-right text-sm tabular-nums">
                                {row.classroom
                                  ? row.classroom.question_count
                                  : `${row.approved_question_count} approved`}
                              </TableCell>
                              <TableCell className="text-right">
                                {row.classroom ? null : (
                                  <Button
                                    type="button"
                                    variant="outline"
                                    size="sm"
                                    disabled={
                                      syncLink.isPending || row.approved_question_count === 0
                                    }
                                    title={
                                      row.approved_question_count === 0
                                        ? "No approved questions to freeze yet"
                                        : undefined
                                    }
                                    onClick={() => void updateClassroomLink(id)}
                                  >
                                    {busy ? "Freezing…" : "Create link"}
                                  </Button>
                                )}
                              </TableCell>
                            </TableRow>
                          );
                        })}
                      </TableBody>
                    </Table>
                  </div>
                ) : null}
              </div>
            </CardContent>
          </Card>
        ) : null}

        {questionSets.isPending ? <TableSkeleton rows={4} /> : null}
        {questionSets.isError ? <QueryError error={questionSets.error} /> : null}

        {questionSets.data && questionSets.data.sets.length === 0 ? (
          <EmptyState
            title="No frozen snapshots for this taxonomy yet"
            hint="Create the classroom link above, or freeze a set on the Coverage page. Links always serve a snapshot, never the live bank."
          />
        ) : null}
      </div>
    </>
  );
}
