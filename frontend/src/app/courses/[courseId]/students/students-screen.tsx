"use client";

import { useQueries } from "@tanstack/react-query";
import { Link as LinkIcon } from "lucide-react";
import type { Route } from "next";
import Link from "next/link";
import { useEffect, useMemo, useState } from "react";
import { toast } from "sonner";
import { CopyButton } from "@/components/copy-button";
import { PageHeader } from "@/components/page-header";
import { EmptyState, QueryError, TableSkeleton } from "@/components/query-state";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import { api, unwrap } from "@/lib/api/client";
import {
  useApprovedCurriculum,
  useQuestionSets,
  useSyncTaxonomyClassroom,
  useTaxonomyClassroom,
} from "@/lib/api/queries";
import type { QuestionDetail, QuestionSetOut } from "@/lib/api/types";
import { SECTIONS_BY_KEY } from "@/lib/navigation";

function formatDate(value: string | null, withTime = false) {
  if (!value) return "Open";
  return new Intl.DateTimeFormat(undefined, {
    dateStyle: "medium",
    ...(withTime ? { timeStyle: "short" } : {}),
  }).format(new Date(value));
}

function newestQuestionSet(sets: QuestionSetOut[]) {
  return [...sets].sort(
    (left, right) => new Date(right.created_at).getTime() - new Date(left.created_at).getTime(),
  )[0];
}

function truncate(value: string, max = 140) {
  if (value.length <= max) return value;
  return `${value.slice(0, max - 1)}…`;
}

type FrozenSetQuestionRow = {
  order: number;
  questionId: number;
  detail: QuestionDetail | null;
};

function hasQuestionDetail(
  entry: FrozenSetQuestionRow,
): entry is FrozenSetQuestionRow & { detail: QuestionDetail } {
  return entry.detail !== null;
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

  const [selectedSetId, setSelectedSetId] = useState<number | null>(null);
  const [showFrozenSetContents, setShowFrozenSetContents] = useState(false);
  const [origin, setOrigin] = useState("");

  useEffect(() => {
    setOrigin(window.location.origin);
  }, []);

  useEffect(() => {
    if (selectedSetId === null && questionSets.data?.sets.length) {
      setSelectedSetId(
        classroom.data?.id ?? newestQuestionSet(questionSets.data.sets)?.id ?? null,
      );
    }
  }, [classroom.data, questionSets.data, selectedSetId]);

  // Switching taxonomy in the header starts again from that taxonomy's own link.
  // biome-ignore lint/correctness/useExhaustiveDependencies: reset only when the taxonomy changes
  useEffect(() => {
    setSelectedSetId(null);
    setShowFrozenSetContents(false);
  }, [taxonomyId]);

  const taxonomyLink = origin && taxonomyId ? `${origin}/students/join?taxonomy=${taxonomyId}` : "";

  const selectedSet = useMemo(
    () => questionSets.data?.sets.find((entry) => entry.id === selectedSetId) ?? null,
    [questionSets.data, selectedSetId],
  );

  const frozenSetQuestions = useQueries({
    queries:
      showFrozenSetContents && selectedSet
        ? selectedSet.question_ids.map((questionId) => ({
            queryKey: ["questions", "detail", questionId],
            queryFn: () =>
              unwrap(
                api.GET("/api/questions/{question_id}", {
                  params: { path: { question_id: questionId } },
                }),
              ),
          }))
        : [],
  });
  const joinLobbyRoute = selectedSet
    ? (`/students/join?set=${selectedSet.id}` as Route)
    : ("/students/join" as Route);

  const frozenSetQuestionRows = useMemo(
    () =>
      selectedSet
        ? selectedSet.question_ids
            .map((questionId, index) => ({
              order: index + 1,
              questionId,
              detail: frozenSetQuestions[index]?.data ?? null,
            }))
            .filter(hasQuestionDetail)
        : [],
    [frozenSetQuestions, selectedSet],
  );

  const frozenSetQuestionsPending =
    showFrozenSetContents && frozenSetQuestions.some((query) => query.isPending);
  const frozenSetQuestionsError = frozenSetQuestions.find((query) => query.isError)?.error ?? null;

  const joinLink = origin && selectedSet ? `${origin}/students/join?set=${selectedSet.id}` : "";

  async function updateClassroomLink() {
    if (taxonomyId === null) return;
    try {
      const synced = await syncLink.mutateAsync(taxonomyId);
      setSelectedSetId(synced.id);
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
        summary="Generate a joinable adaptive-training classroom from a frozen question set. Enrolled learners and their progress live on the Roster page."
        actions={
          questionSets.data ? (
            <Badge
              variant="outline"
              className="h-7 rounded-full px-3 font-mono tracking-[0.08em]"
            >
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
              <p className="text-muted-foreground text-sm">
                This taxonomy's own link. It never changes; updating it freezes the taxonomy's
                approved questions as a new snapshot, and new learners get that snapshot. Learners
                already in a run keep the one they started on. Switch taxonomy at the top right to
                get another taxonomy's link.
              </p>
            </CardHeader>
            <CardContent className="space-y-3">
              {classroom.data ? (
                <>
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
                  <p className="text-muted-foreground text-sm">
                    Serving snapshot #{classroom.data.id} · {classroom.data.question_count}{" "}
                    questions · frozen {formatDate(classroom.data.created_at, true)}
                  </p>
                </>
              ) : classroom.isPending ? (
                <TableSkeleton rows={1} />
              ) : (
                <p className="text-muted-foreground text-sm">
                  No classroom link yet. Creating it freezes this taxonomy's approved questions.
                </p>
              )}
              {syncLink.error ? <QueryError error={syncLink.error} /> : null}
              <Button
                type="button"
                variant={classroom.data ? "outline" : "default"}
                size="sm"
                disabled={syncLink.isPending}
                onClick={() => void updateClassroomLink()}
              >
                {syncLink.isPending
                  ? "Freezing…"
                  : classroom.data
                    ? "Update to the current approved questions"
                    : "Create classroom link"}
              </Button>
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

        {selectedSet ? (
          <div className="grid gap-4 xl:grid-cols-[1.5fr_1fr]">
            <Card className="border-border/70">
              <CardHeader className="gap-3">
                <div className="flex items-center gap-2 text-muted-foreground text-xs uppercase tracking-[0.18em]">
                  <LinkIcon className="size-3.5" />
                  One snapshot
                </div>
                <CardTitle className="text-xl">{selectedSet.label}</CardTitle>
              </CardHeader>
              <CardContent className="space-y-4">
                <div className="grid gap-3 md:grid-cols-3">
                  <div className="rounded-xl border border-border/70 bg-muted/30 p-3">
                    <div className="text-muted-foreground text-xs uppercase tracking-[0.14em]">
                      Frozen set
                    </div>
                    <div className="mt-2 font-semibold text-lg">
                      {classroom.data?.id === selectedSet.id
                        ? `#${selectedSet.id} · behind the link`
                        : `#${selectedSet.id}`}
                    </div>
                  </div>
                  <div className="rounded-xl border border-border/70 bg-muted/30 p-3">
                    <div className="text-muted-foreground text-xs uppercase tracking-[0.14em]">
                      Questions
                    </div>
                    <div className="mt-2 font-semibold text-lg">
                      {selectedSet.member_count} / {selectedSet.question_count}
                    </div>
                  </div>
                  <div className="rounded-xl border border-border/70 bg-muted/30 p-3">
                    <div className="text-muted-foreground text-xs uppercase tracking-[0.14em]">
                      Frozen on
                    </div>
                    <div className="mt-2 font-semibold text-lg">
                      {formatDate(selectedSet.created_at)}
                    </div>
                  </div>
                </div>

                <div className="space-y-2">
                  <label className="font-medium text-sm" htmlFor="classroom-link">
                    Join link
                  </label>
                  <div className="flex flex-col gap-2 md:flex-row">
                    <Input
                      id="classroom-link"
                      value={joinLink}
                      readOnly
                      className="font-mono text-xs"
                    />
                    <div className="flex gap-2">
                      <CopyButton text={joinLink} label="Copy link" copiedLabel="Copied" />
                      <Button asChild variant="secondary" size="sm">
                        <Link href={joinLobbyRoute}>Open lobby</Link>
                      </Button>
                    </div>
                  </div>
                  <p className="text-muted-foreground text-sm">
                    A link to this one snapshot. It never moves to a newer one; for that, share
                    the classroom link above.
                  </p>
                </div>

                <div className="space-y-3 border-border/60 border-t pt-4">
                  <div className="flex items-center justify-between gap-3">
                    <div>
                      <div className="font-medium text-sm">Frozen set contents</div>
                      <p className="text-muted-foreground text-sm">
                        Inspect the exact questions included in snapshot #{selectedSet.id}.
                      </p>
                    </div>
                    <Button
                      type="button"
                      variant="outline"
                      size="sm"
                      onClick={() => setShowFrozenSetContents((current) => !current)}
                    >
                      {showFrozenSetContents ? "Hide contents" : "View contents"}
                    </Button>
                  </div>

                  {showFrozenSetContents ? (
                    <>
                      {frozenSetQuestionsPending ? <TableSkeleton rows={4} /> : null}
                      {frozenSetQuestionsError ? (
                        <QueryError error={frozenSetQuestionsError} />
                      ) : null}

                      {!frozenSetQuestionsPending && !frozenSetQuestionsError ? (
                        <div className="rounded-xl border border-border/70">
                          <Table>
                            <TableHeader>
                              <TableRow>
                                <TableHead>#</TableHead>
                                <TableHead>Question</TableHead>
                                <TableHead>Type</TableHead>
                                <TableHead>Difficulty</TableHead>
                                <TableHead>Status</TableHead>
                              </TableRow>
                            </TableHeader>
                            <TableBody>
                              {frozenSetQuestionRows.map(({ order, questionId, detail }) => (
                                <TableRow key={questionId}>
                                  <TableCell className="font-medium">#{questionId}</TableCell>
                                  <TableCell className="max-w-[38rem]">
                                    <div className="space-y-1">
                                      <div className="text-muted-foreground text-xs">
                                        Item {order} in set
                                      </div>
                                      <div>{truncate(detail.question.prompt)}</div>
                                    </div>
                                  </TableCell>
                                  <TableCell className="capitalize">
                                    {detail.question.question_type
                                      ? detail.question.question_type.replaceAll("_", " ")
                                      : "—"}
                                  </TableCell>
                                  <TableCell className="capitalize">
                                    {detail.question.difficulty}
                                  </TableCell>
                                  <TableCell className="capitalize">
                                    {detail.question.status.replaceAll("_", " ")}
                                  </TableCell>
                                </TableRow>
                              ))}
                            </TableBody>
                          </Table>
                        </div>
                      ) : null}
                    </>
                  ) : null}
                </div>
              </CardContent>
            </Card>

            <Card className="border-border/70">
              <CardHeader>
                <CardTitle className="text-base">Available frozen sets</CardTitle>
              </CardHeader>
              <CardContent className="space-y-3">
                <Select
                  value={selectedSet.id.toString()}
                  onValueChange={(value) => setSelectedSetId(Number(value))}
                >
                  <SelectTrigger aria-label="Choose classroom set">
                    <SelectValue />
                  </SelectTrigger>
                  <SelectContent>
                    {questionSets.data?.sets.map((entry) => (
                      <SelectItem key={entry.id} value={entry.id.toString()}>
                        #{entry.id} · {entry.label}
                      </SelectItem>
                    ))}
                  </SelectContent>
                </Select>

                <Table>
                  <TableHeader>
                    <TableRow>
                      <TableHead>Set</TableHead>
                      <TableHead>Questions</TableHead>
                      <TableHead>Created</TableHead>
                    </TableRow>
                  </TableHeader>
                  <TableBody>
                    {questionSets.data?.sets.map((entry) => (
                      <TableRow
                        key={entry.id}
                        className={entry.id === selectedSet.id ? "bg-muted/40" : undefined}
                        onClick={() => setSelectedSetId(entry.id)}
                      >
                        <TableCell className="font-medium">
                          {classroom.data?.id === entry.id ? `#${entry.id} · link` : `#${entry.id}`}
                        </TableCell>
                        <TableCell>{entry.member_count}</TableCell>
                        <TableCell>{formatDate(entry.created_at)}</TableCell>
                      </TableRow>
                    ))}
                  </TableBody>
                </Table>
              </CardContent>
            </Card>
          </div>
        ) : null}
      </div>
    </>
  );
}
