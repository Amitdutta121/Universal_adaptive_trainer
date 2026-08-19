"use client";

import { BookOpenCheck, GraduationCap, Link as LinkIcon, Play, UserPlus } from "lucide-react";
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
import { Progress } from "@/components/ui/progress";
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
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import {
  useCreateStudent,
  useQuestionSets,
  useStartTrainingSession,
  useStudentProgress,
  useStudents,
} from "@/lib/api/queries";
import type { QuestionSetOut, StudentOut } from "@/lib/api/types";
import { SECTIONS_BY_KEY } from "@/lib/navigation";

function formatDate(value: string | null, withTime = false) {
  if (!value) return "Open";
  return new Intl.DateTimeFormat(undefined, {
    dateStyle: "medium",
    ...(withTime ? { timeStyle: "short" } : {}),
  }).format(new Date(value));
}

function percent(value: number | null) {
  if (value === null) return "—";
  return `${value.toFixed(1)} / 100`;
}

function masteryPercent(value: number) {
  return Math.max(0, Math.min(100, value * 100));
}

function newestQuestionSet(sets: QuestionSetOut[]) {
  return [...sets].sort(
    (left, right) => new Date(right.created_at).getTime() - new Date(left.created_at).getTime(),
  )[0];
}

export function StudentsScreen() {
  const section = SECTIONS_BY_KEY.students;
  const students = useStudents();
  const questionSets = useQuestionSets();
  const createStudent = useCreateStudent();
  const startTrainingSession = useStartTrainingSession();

  const [studentName, setStudentName] = useState("");
  const [selectedStudentId, setSelectedStudentId] = useState<number | null>(null);
  const [selectedSetId, setSelectedSetId] = useState<number | null>(null);
  const [origin, setOrigin] = useState("");

  useEffect(() => {
    setOrigin(window.location.origin);
  }, []);

  useEffect(() => {
    if (selectedStudentId === null && students.data?.students.length) {
      setSelectedStudentId(students.data.students[0]?.id ?? null);
    }
  }, [students.data, selectedStudentId]);

  useEffect(() => {
    if (selectedSetId === null && questionSets.data?.sets.length) {
      setSelectedSetId(newestQuestionSet(questionSets.data.sets)?.id ?? null);
    }
  }, [questionSets.data, selectedSetId]);

  const selectedSet = useMemo(
    () => questionSets.data?.sets.find((entry) => entry.id === selectedSetId) ?? null,
    [questionSets.data, selectedSetId],
  );

  const selectedStudent = useMemo(
    () => students.data?.students.find((entry) => entry.id === selectedStudentId) ?? null,
    [students.data, selectedStudentId],
  );
  const joinLobbyRoute = selectedSet
    ? (`/students/join?set=${selectedSet.id}` as Route)
    : ("/students/join" as Route);

  const progress = useStudentProgress(selectedStudentId, {
    enabled: selectedStudentId !== null,
  });

  const joinLink = origin && selectedSet ? `${origin}/students/join?set=${selectedSet.id}` : "";

  const activeRuns =
    progress.data?.sessions.filter((session) => session.ended_at === null).length ?? 0;

  const handleCreateStudent = () => {
    const displayName = studentName.trim();
    if (!displayName) return;
    createStudent.mutate(
      { display_name: displayName },
      {
        onSuccess: (created) => {
          setStudentName("");
          setSelectedStudentId(created.id);
        },
      },
    );
  };

  const handleStartRun = (student: StudentOut) => {
    if (!selectedSet) return;
    startTrainingSession.mutate({
      student_id: student.id,
      set_version_id: selectedSet.id,
    });
  };

  return (
    <>
      <PageHeader
        title={section.label}
        summary="Generate a joinable adaptive-training classroom from a frozen question set, then manage enrolled learners and live runs."
        actions={
          students.data ? (
            <Badge variant="outline" className="h-7 rounded-full px-3 font-mono tracking-[0.08em]">
              {students.data.total} learners
            </Badge>
          ) : null
        }
      />

      <Tabs defaultValue="classrooms" className="space-y-4">
        <TabsList>
          <TabsTrigger value="classrooms">Classrooms</TabsTrigger>
          <TabsTrigger value="roster">Roster</TabsTrigger>
        </TabsList>

        <TabsContent value="classrooms" className="space-y-4">
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
                        Frozen set
                      </div>
                      <div className="mt-2 font-semibold text-lg">#{selectedSet.id}</div>
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
                      Anyone with this link can enter a learner name, create a training session, and
                      start adaptive practice against this frozen set.
                    </p>
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
                          <TableCell className="font-medium">#{entry.id}</TableCell>
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
        </TabsContent>

        <TabsContent value="roster" className="space-y-4">
          <div className="grid gap-4 xl:grid-cols-[1.2fr_0.8fr]">
            <Card className="border-border/70">
              <CardHeader className="gap-3">
                <div className="flex items-center gap-2 text-muted-foreground text-xs uppercase tracking-[0.18em]">
                  <GraduationCap className="size-3.5" />
                  Learner management
                </div>
                <CardTitle className="text-xl">Enrolled students</CardTitle>
              </CardHeader>
              <CardContent className="space-y-4">
                <div className="flex flex-col gap-2 md:flex-row">
                  <Input
                    value={studentName}
                    onChange={(event) => setStudentName(event.target.value)}
                    placeholder="e.g. Ada Lovelace"
                    maxLength={200}
                    onKeyDown={(event) => {
                      if (event.key === "Enter") {
                        event.preventDefault();
                        handleCreateStudent();
                      }
                    }}
                  />
                  <Button
                    type="button"
                    onClick={handleCreateStudent}
                    disabled={createStudent.isPending || studentName.trim().length === 0}
                  >
                    <UserPlus />
                    Enrol student
                  </Button>
                </div>

                {createStudent.isError ? <QueryError error={createStudent.error} /> : null}
                {students.isPending ? <TableSkeleton rows={5} /> : null}
                {students.isError ? <QueryError error={students.error} /> : null}

                {students.isSuccess && students.data.students.length === 0 ? (
                  <EmptyState
                    title="No students enrolled yet"
                    hint="You can enrol a learner directly here, or send a classroom link and let each learner create their own name."
                  />
                ) : null}

                {students.data?.students.length ? (
                  <Table>
                    <TableHeader>
                      <TableRow>
                        <TableHead>Name</TableHead>
                        <TableHead>Answered</TableHead>
                        <TableHead>Enrolled</TableHead>
                        <TableHead className="text-right">Actions</TableHead>
                      </TableRow>
                    </TableHeader>
                    <TableBody>
                      {students.data.students.map((student) => (
                        <TableRow
                          key={student.id}
                          className={student.id === selectedStudentId ? "bg-muted/40" : undefined}
                        >
                          <TableCell className="font-medium">{student.display_name}</TableCell>
                          <TableCell>{student.answered_count}</TableCell>
                          <TableCell>{formatDate(student.created_at)}</TableCell>
                          <TableCell className="text-right">
                            <div className="flex justify-end gap-2">
                              <Button
                                type="button"
                                variant="outline"
                                size="sm"
                                onClick={() => setSelectedStudentId(student.id)}
                              >
                                Manage
                              </Button>
                              <Button
                                type="button"
                                size="sm"
                                disabled={!selectedSet || startTrainingSession.isPending}
                                onClick={() => handleStartRun(student)}
                              >
                                <Play />
                                Start run
                              </Button>
                            </div>
                          </TableCell>
                        </TableRow>
                      ))}
                    </TableBody>
                  </Table>
                ) : null}
              </CardContent>
            </Card>

            <Card className="border-border/70">
              <CardHeader className="gap-3">
                <div className="flex items-center gap-2 text-muted-foreground text-xs uppercase tracking-[0.18em]">
                  <Play className="size-3.5" />
                  Current selection
                </div>
                <CardTitle className="text-xl">
                  {selectedStudent?.display_name ?? "Choose a learner"}
                </CardTitle>
              </CardHeader>
              <CardContent className="space-y-4">
                {startTrainingSession.isError ? (
                  <QueryError error={startTrainingSession.error} />
                ) : null}

                {selectedStudent === null ? (
                  <EmptyState
                    title="No learner selected"
                    hint="Pick one from the roster to inspect progress and manage their runs."
                  />
                ) : (
                  <>
                    <div className="grid gap-3 sm:grid-cols-3">
                      <div className="rounded-xl border border-border/70 bg-muted/30 p-3">
                        <div className="text-muted-foreground text-xs uppercase tracking-[0.14em]">
                          Answered
                        </div>
                        <div className="mt-2 font-semibold text-lg">
                          {progress.data?.answered ?? selectedStudent.answered_count}
                        </div>
                      </div>
                      <div className="rounded-xl border border-border/70 bg-muted/30 p-3">
                        <div className="text-muted-foreground text-xs uppercase tracking-[0.14em]">
                          Average score
                        </div>
                        <div className="mt-2 font-semibold text-lg">
                          {percent(progress.data?.average_score ?? null)}
                        </div>
                      </div>
                      <div className="rounded-xl border border-border/70 bg-muted/30 p-3">
                        <div className="text-muted-foreground text-xs uppercase tracking-[0.14em]">
                          Active runs
                        </div>
                        <div className="mt-2 font-semibold text-lg">{activeRuns}</div>
                      </div>
                    </div>

                    <div className="space-y-2">
                      <label className="font-medium text-sm" htmlFor="set-selection">
                        Start a new run from
                      </label>
                      <Select
                        value={selectedSetId?.toString() ?? ""}
                        onValueChange={(value) => setSelectedSetId(Number(value))}
                        disabled={!questionSets.data?.sets.length}
                      >
                        <SelectTrigger id="set-selection" aria-label="Choose set for new run">
                          <SelectValue placeholder="Choose a frozen set" />
                        </SelectTrigger>
                        <SelectContent>
                          {questionSets.data?.sets.map((entry) => (
                            <SelectItem key={entry.id} value={entry.id.toString()}>
                              #{entry.id} · {entry.label}
                            </SelectItem>
                          ))}
                        </SelectContent>
                      </Select>
                      <Button
                        type="button"
                        className="w-full"
                        disabled={!selectedSet || startTrainingSession.isPending}
                        onClick={() => handleStartRun(selectedStudent)}
                      >
                        <Play />
                        Start run for {selectedStudent.display_name}
                      </Button>
                    </div>
                  </>
                )}
              </CardContent>
            </Card>
          </div>

          {progress.isPending ? <TableSkeleton rows={6} /> : null}
          {progress.isError ? <QueryError error={progress.error} /> : null}

          {progress.data ? (
            <div className="grid gap-4 2xl:grid-cols-[0.95fr_1.05fr]">
              <Card className="border-border/70">
                <CardHeader>
                  <CardTitle className="text-base">Topic mastery</CardTitle>
                </CardHeader>
                <CardContent>
                  {progress.data.topics.length === 0 ? (
                    <EmptyState
                      title="Nothing measured yet"
                      hint="Mastery appears once at least one question has been scored."
                    />
                  ) : (
                    <div className="space-y-4">
                      {progress.data.topics.map((topic) => (
                        <div key={topic.topic_id} className="space-y-2">
                          <div className="flex items-center justify-between gap-2">
                            <div>
                              <div className="font-medium">{topic.topic_name}</div>
                              <div className="text-muted-foreground text-xs">
                                Next difficulty: {topic.next_difficulty} · {topic.observations}{" "}
                                score(s)
                              </div>
                            </div>
                            <Badge variant={topic.band === "high" ? "secondary" : "outline"}>
                              {topic.band}
                            </Badge>
                          </div>
                          <Progress value={masteryPercent(topic.p_known)} />
                        </div>
                      ))}
                    </div>
                  )}
                </CardContent>
              </Card>

              <Card className="border-border/70">
                <CardHeader>
                  <CardTitle className="text-base">Training runs</CardTitle>
                </CardHeader>
                <CardContent>
                  {progress.data.sessions.length === 0 ? (
                    <EmptyState
                      title="No training runs yet"
                      hint="Start a run from a frozen set to begin tracking adaptive progress."
                    />
                  ) : (
                    <Table>
                      <TableHeader>
                        <TableRow>
                          <TableHead>Run</TableHead>
                          <TableHead>Set</TableHead>
                          <TableHead>Answered</TableHead>
                          <TableHead>Started</TableHead>
                          <TableHead>Status</TableHead>
                        </TableRow>
                      </TableHeader>
                      <TableBody>
                        {progress.data.sessions.map((session) => (
                          <TableRow key={session.id}>
                            <TableCell className="font-medium">#{session.id}</TableCell>
                            <TableCell>
                              {session.set_label ?? `Set #${session.set_version_id ?? "?"}`}
                            </TableCell>
                            <TableCell>
                              {session.answered_count} / {session.served_count}
                            </TableCell>
                            <TableCell>{formatDate(session.created_at, true)}</TableCell>
                            <TableCell>
                              {session.ended_at ? (
                                <span className="text-muted-foreground">Closed</span>
                              ) : (
                                <Button asChild variant="outline" size="sm">
                                  <Link href={`/students/join/session/${session.id}` as Route}>
                                    Resume
                                  </Link>
                                </Button>
                              )}
                            </TableCell>
                          </TableRow>
                        ))}
                      </TableBody>
                    </Table>
                  )}
                </CardContent>
              </Card>
            </div>
          ) : null}
        </TabsContent>
      </Tabs>
    </>
  );
}
