"use client";

import { useQueries } from "@tanstack/react-query";
import { BookOpenCheck, Link as LinkIcon } from "lucide-react";
import type { Route } from "next";
import Link from "next/link";
import { useEffect, useMemo, useState } from "react";
import { CopyButton } from "@/components/copy-button";
import { PageHeader } from "@/components/page-header";
import { EmptyState, QueryError, TableSkeleton } from "@/components/query-state";
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
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
import { useProdQuestionSet, useQuestionSets } from "@/lib/api/queries";
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
  const questionSets = useQuestionSets();
  const prodQuestionSet = useProdQuestionSet();

  const [selectedSetId, setSelectedSetId] = useState<number | null>(null);
  const [showFrozenSetContents, setShowFrozenSetContents] = useState(false);
  const [origin, setOrigin] = useState("");

  useEffect(() => {
    setOrigin(window.location.origin);
  }, []);

  useEffect(() => {
    if (selectedSetId === null && questionSets.data?.sets.length) {
      setSelectedSetId(
        prodQuestionSet.data?.id ?? newestQuestionSet(questionSets.data.sets)?.id ?? null,
      );
    }
  }, [prodQuestionSet.data, questionSets.data, selectedSetId]);

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
    ? ((selectedSet.is_prod
        ? "/students/join?set=prod"
        : `/students/join?set=${selectedSet.id}`) as Route)
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

  const joinLink =
    origin && selectedSet
      ? `${origin}/students/join?set=${selectedSet.is_prod ? "prod" : selectedSet.id}`
      : "";

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
        {questionSets.isPending ? <TableSkeleton rows={4} /> : null}
        {questionSets.isError ? <QueryError error={questionSets.error} /> : null}

        {questionSets.isSuccess && questionSets.data.sets.length === 0 ? (
          <EmptyState
            title="No frozen classroom sets yet"
            hint="Freeze a question set on the Coverage page first. Classroom links always target a snapshot, never the live bank."
          />
        ) : null}

        {selectedSet ? (
          <div className="grid gap-4 xl:grid-cols-[1.5fr_1fr]">
            <Card className="border-border/70">
              <CardHeader className="gap-3">
                <div className="flex items-center gap-2 text-muted-foreground text-xs uppercase tracking-[0.18em]">
                  <LinkIcon className="size-3.5" />
                  Shareable classroom
                </div>
                <CardTitle className="text-xl">{selectedSet.label}</CardTitle>
              </CardHeader>
              <CardContent className="space-y-4">
                <div className="grid gap-3 md:grid-cols-3">
                  <div className="rounded-xl border border-border/70 bg-muted/30 p-3">
                    <div className="text-muted-foreground text-xs uppercase tracking-[0.14em]">
                      {selectedSet.is_prod ? "Prod set" : "Frozen set"}
                    </div>
                    <div className="mt-2 font-semibold text-lg">
                      {selectedSet.is_prod
                        ? `Live link -> #${selectedSet.id}`
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

                {selectedSet.notes ? (
                  <Alert>
                    <BookOpenCheck />
                    <AlertTitle>Professor notes</AlertTitle>
                    <AlertDescription>{selectedSet.notes}</AlertDescription>
                  </Alert>
                ) : null}

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
                    {selectedSet.is_prod
                      ? "Anyone with this link joins the current production classroom. Existing runs stay pinned to the snapshot they started on."
                      : "Anyone with this link can enter a learner name, create a training session, and start adaptive practice against this frozen set."}
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
                        {entry.is_prod ? "Prod classroom" : `#${entry.id}`} · {entry.label}
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
                          {entry.is_prod ? `Prod -> #${entry.id}` : `#${entry.id}`}
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
