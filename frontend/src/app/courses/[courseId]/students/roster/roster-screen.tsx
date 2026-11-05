"use client";

import { GraduationCap } from "lucide-react";
import type { Route } from "next";
import Link from "next/link";
import { useSearchParams } from "next/navigation";
import { useEffect, useMemo, useRef, useState } from "react";
import {
  CartesianGrid,
  Line,
  LineChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import { PageHeader } from "@/components/page-header";
import { EmptyState, QueryError, TableSkeleton } from "@/components/query-state";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Progress } from "@/components/ui/progress";
import { pluralise } from "@/lib/display";
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
import {
  useApprovedCurriculum,
  useClassSummary,
  useCurriculumVersions,
  useStudentProgress,
  useStudents,
} from "@/lib/api/queries";
import type { ClassSummary } from "@/lib/api/types";
import { ClassWeaknessCard } from "../class-weakness-card";
import { buildClassScoreTrend, buildScoreTrend, type ClassTrendAttempt } from "../score-trend";

const PAGE_SIZE = 20;

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

function scoreLabel(value: number) {
  return `${value.toFixed(0)} / 100`;
}

type ScoreFilter = "all" | "lt50" | "50to70" | "70to85" | "85plus";
type AnsweredFilter = "all" | "0" | "1to5" | "6to20" | "21plus";
type ActivityFilter = "all" | "today" | "last7" | "last30" | "inactive";

function MiniAverageTrend({ values }: { values: number[] }) {
  if (values.length === 0) {
    return (
      <div className="flex h-10 w-24 items-center justify-center rounded-lg border border-border/70 border-dashed text-[11px] text-muted-foreground">
        No scores
      </div>
    );
  }

  const width = 96;
  const height = 40;
  const points = values
    .map((value, index) => {
      const x = values.length === 1 ? width / 2 : (index / (values.length - 1)) * width;
      const y = height - (Math.max(0, Math.min(100, value)) / 100) * height;
      return `${x},${y}`;
    })
    .join(" ");

  return (
    <div className="space-y-1">
      <svg
        viewBox={`0 0 ${width} ${height}`}
        className="h-10 w-24 overflow-visible rounded-lg border border-border/60 bg-muted/20"
        aria-hidden="true"
      >
        <polyline
          fill="none"
          stroke="var(--primary)"
          strokeWidth="2.5"
          strokeLinecap="round"
          strokeLinejoin="round"
          points={points}
        />
      </svg>
      <div className="text-right text-[11px] text-muted-foreground">Avg</div>
    </div>
  );
}

function chartLabel(timestamp: string, sequence: number, total: number) {
  return `Attempt ${sequence} of ${total} · ${formatDate(timestamp, true)}`;
}

function masteryPercent(value: number) {
  return Math.max(0, Math.min(100, value * 100));
}

function topicBandStyles(band: "low" | "medium" | "high") {
  if (band === "high") {
    return {
      badgeClassName: "border-emerald-200 bg-emerald-50 text-emerald-700",
      progressClassName: "bg-emerald-600",
    };
  }
  if (band === "medium") {
    return {
      badgeClassName: "border-amber-200 bg-amber-50 text-amber-700",
      progressClassName: "bg-amber-500",
    };
  }
  return {
    badgeClassName: "border-rose-200 bg-rose-50 text-rose-700",
    progressClassName: "bg-rose-500",
  };
}

/** Regroup the flat class-summary attempt list into the per-student shape the
 * class trend builder expects. */
function groupAttemptsByStudent(
  attempts: NonNullable<ClassSummary["scored_attempts"]>,
): Array<{ attempts: ClassTrendAttempt[]; studentId: number }> {
  const byStudent = new Map<number, ClassTrendAttempt[]>();
  for (const attempt of attempts) {
    const bucket = byStudent.get(attempt.student_id);
    if (bucket) bucket.push(attempt);
    else byStudent.set(attempt.student_id, [attempt]);
  }
  return [...byStudent.entries()].map(([studentId, studentAttempts]) => ({
    studentId,
    attempts: studentAttempts,
  }));
}

export function RosterScreen() {
  // Students table "Details" deep-links here with ?search=&student=&taxonomy=.
  const searchParams = useSearchParams();
  const initialSearch = searchParams.get("search")?.trim() ?? "";
  const initialStudent = Number(searchParams.get("student"));
  const initialTaxonomy = searchParams.get("taxonomy");
  const [searchInput, setSearchInput] = useState(initialSearch);
  const [searchTerm, setSearchTerm] = useState(initialSearch);
  const [scoreFilter, setScoreFilter] = useState<ScoreFilter>("all");
  const [answeredFilter, setAnsweredFilter] = useState<AnsweredFilter>("all");
  const [activityFilter, setActivityFilter] = useState<ActivityFilter>("all");
  const [curriculumFilter, setCurriculumFilter] = useState<string>(initialTaxonomy ?? "all");
  const [page, setPage] = useState(1);
  const [selectedStudentId, setSelectedStudentId] = useState<number | null>(
    Number.isInteger(initialStudent) && initialStudent > 0 ? initialStudent : null,
  );
  // A deep-linked taxonomy wins over the first active-taxonomy sync below.
  const keepLinkedTaxonomy = useRef(initialTaxonomy !== null);

  // Debounce the search box so a keystroke is not a request. A settled search
  // term is a new query, so it restarts at the first page.
  useEffect(() => {
    const timer = setTimeout(() => {
      setSearchTerm(searchInput.trim());
      setPage(1);
    }, 250);
    return () => clearTimeout(timer);
  }, [searchInput]);

  // The dropdown filters reset the page the same way (see their onValueChange).
  function pickFilter<T>(set: (value: T) => void, value: T) {
    set(value);
    setPage(1);
  }

  const curriculumVersions = useCurriculumVersions();
  const approvedCurriculum = useApprovedCurriculum();
  const activeVersionId = approvedCurriculum.data?.version.id ?? null;

  // The roster follows the app's active taxonomy by default -- picking a new
  // one in the header selector re-filters the list, not just this page's own
  // dropdown. A professor can still override to "all" or another version below;
  // that override holds until the active taxonomy changes again.
  useEffect(() => {
    if (activeVersionId !== null) {
      if (keepLinkedTaxonomy.current) {
        keepLinkedTaxonomy.current = false;
        return;
      }
      setCurriculumFilter(String(activeVersionId));
      setPage(1);
    }
  }, [activeVersionId]);

  const curriculumVersionId = curriculumFilter === "all" ? null : Number(curriculumFilter);

  const list = useStudents({
    search: searchTerm,
    score: scoreFilter,
    answered: answeredFilter,
    activity: activityFilter,
    curriculumVersionId,
    page,
    pageSize: PAGE_SIZE,
  });
  const summary = useClassSummary(curriculumVersionId);

  const rows = list.data?.students ?? [];
  const total = list.data?.total ?? 0;
  const pageSize = list.data?.page_size ?? PAGE_SIZE;
  const pageCount = Math.max(1, Math.ceil(total / pageSize));
  const isFiltered =
    searchTerm.length > 0 ||
    scoreFilter !== "all" ||
    answeredFilter !== "all" ||
    activityFilter !== "all" ||
    curriculumFilter !== "all";

  // Land on the first learner of the page until the professor picks one, and
  // re-land if a filter change (e.g. switching taxonomy) drops the current
  // selection out of the visible rows entirely.
  useEffect(() => {
    if (rows.length === 0) return;
    if (selectedStudentId === null || !rows.some((row) => row.id === selectedStudentId)) {
      setSelectedStudentId(rows[0]?.id ?? null);
    }
  }, [rows, selectedStudentId]);

  const classScoreTrend = useMemo(
    () => buildClassScoreTrend(groupAttemptsByStudent(summary.data?.scored_attempts ?? [])),
    [summary.data?.scored_attempts],
  );
  const classSolvedQuestions = classScoreTrend.at(-1)?.totalSolved ?? 0;
  const classStudentsIncluded = classScoreTrend.at(-1)?.studentsIncluded ?? 0;

  const progress = useStudentProgress(selectedStudentId, {
    enabled: selectedStudentId !== null,
  });
  const selectedStudent = progress.data?.student ?? null;
  const totalSessions = progress.data?.sessions.length ?? 0;
  const scoreTrend = useMemo(
    () => buildScoreTrend(progress.data?.recent_attempts ?? []),
    [progress.data?.recent_attempts],
  );

  return (
    <>
      <PageHeader
        title="Roster"
        summary="Every enrolled learner's adaptive-training progress: score trends, topic mastery, class weakness, and session history."
        actions={
          list.data ? (
            <Badge
              variant="outline"
              className="h-7 rounded-full px-3 font-mono tracking-[0.08em]"
            >
              {total} learner{total === 1 ? "" : "s"}
            </Badge>
          ) : null
        }
      />

      <div className="grid gap-4 xl:grid-cols-[0.78fr_1.22fr]">
        <Card className="border-border/70">
          <CardHeader className="gap-3">
            <div className="flex items-center gap-2 text-muted-foreground text-xs uppercase tracking-[0.18em]">
              <GraduationCap className="size-3.5" />
              Learner management
            </div>
            <CardTitle className="text-xl">Search students</CardTitle>
          </CardHeader>
          <CardContent className="space-y-4">
            <Input
              aria-label="Search students"
              value={searchInput}
              onChange={(event) => setSearchInput(event.target.value)}
              placeholder="Search students"
              maxLength={200}
            />
            <div className="grid gap-2 md:grid-cols-2">
              <Select
                value={scoreFilter}
                onValueChange={(value) => pickFilter(setScoreFilter, value as ScoreFilter)}
              >
                <SelectTrigger aria-label="Filter by average score">
                  <SelectValue placeholder="Average score" />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="all">Average score: all</SelectItem>
                  <SelectItem value="lt50">Below 50</SelectItem>
                  <SelectItem value="50to70">50 to 69</SelectItem>
                  <SelectItem value="70to85">70 to 84</SelectItem>
                  <SelectItem value="85plus">85 and above</SelectItem>
                </SelectContent>
              </Select>
              <Select
                value={answeredFilter}
                onValueChange={(value) => pickFilter(setAnsweredFilter, value as AnsweredFilter)}
              >
                <SelectTrigger aria-label="Filter by answered count">
                  <SelectValue placeholder="Answered count" />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="all">Answered: all</SelectItem>
                  <SelectItem value="0">0 answered</SelectItem>
                  <SelectItem value="1to5">1 to 5 answered</SelectItem>
                  <SelectItem value="6to20">6 to 20 answered</SelectItem>
                  <SelectItem value="21plus">21+ answered</SelectItem>
                </SelectContent>
              </Select>
              <Select
                value={activityFilter}
                onValueChange={(value) => pickFilter(setActivityFilter, value as ActivityFilter)}
              >
                <SelectTrigger aria-label="Filter by recent activity">
                  <SelectValue placeholder="Recent activity" />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="all">Recent activity: all</SelectItem>
                  <SelectItem value="today">Active today</SelectItem>
                  <SelectItem value="last7">Active in last 7 days</SelectItem>
                  <SelectItem value="last30">Active in last 30 days</SelectItem>
                  <SelectItem value="inactive">Inactive</SelectItem>
                </SelectContent>
              </Select>
              <Select
                value={curriculumFilter}
                onValueChange={(value) => pickFilter(setCurriculumFilter, value)}
              >
                <SelectTrigger aria-label="Filter by taxonomy">
                  <SelectValue placeholder="Taxonomy" />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="all">Taxonomy: all</SelectItem>
                  {(curriculumVersions.data?.versions ?? []).map((version) => (
                    <SelectItem key={version.id} value={String(version.id)}>
                      {version.label}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>
            {list.isPending ? <TableSkeleton rows={5} /> : null}
            {list.isError ? <QueryError error={list.error} /> : null}

            {list.isSuccess && total === 0 ? (
              isFiltered ? (
                <EmptyState
                  title="No matching students"
                  hint="Loosen the search or filters to see more learners."
                />
              ) : (
                <EmptyState
                  title="No students yet"
                  hint="Students appear here after they join from a classroom link."
                />
              )
            ) : null}

            {rows.length ? (
              <div
                className={`space-y-2 transition-opacity ${
                  list.isPlaceholderData ? "opacity-60" : ""
                }`}
              >
                {rows.map((student) => (
                  <button
                    key={student.id}
                    type="button"
                    onClick={() => setSelectedStudentId(student.id)}
                    className={`w-full rounded-xl border p-4 text-left transition-colors ${
                      student.id === selectedStudentId
                        ? "border-primary/40 bg-primary/10 shadow-sm ring-2 ring-primary/20"
                        : "border-border/70 bg-background hover:border-border hover:bg-muted/30"
                    }`}
                  >
                    <div className="flex items-start justify-between gap-3">
                      <div className="space-y-1">
                        <div className="flex flex-wrap items-center gap-2">
                          <div className="font-medium">{student.display_name}</div>
                          {student.id === selectedStudentId ? (
                            <span className="rounded-full bg-primary/15 px-2 py-0.5 font-medium text-[11px] text-primary uppercase tracking-[0.12em]">
                              Selected
                            </span>
                          ) : null}
                        </div>
                        {student.email ? (
                          <div className="text-muted-foreground text-sm">{student.email}</div>
                        ) : null}
                        <div className="text-muted-foreground text-sm">
                          Enrolled {formatDate(student.created_at)}
                        </div>
                      </div>
                      <div className="flex flex-col items-end gap-2">
                        <MiniAverageTrend values={student.score_series ?? []} />
                        <Badge
                          variant={student.id === selectedStudentId ? "secondary" : "outline"}
                        >
                          {student.answered_count} answered
                        </Badge>
                      </div>
                    </div>
                  </button>
                ))}
              </div>
            ) : null}

            {total > 0 ? (
              <div className="flex items-center justify-between gap-3 border-border/60 border-t pt-3 text-sm">
                <span className="text-muted-foreground">
                  Page {page} of {pageCount} · {total} {isFiltered ? "matching" : ""} learner
                  {total === 1 ? "" : "s"}
                </span>
                <div className="flex gap-2">
                  <Button
                    type="button"
                    variant="outline"
                    size="sm"
                    disabled={page <= 1 || list.isPlaceholderData}
                    onClick={() => setPage((current) => Math.max(1, current - 1))}
                  >
                    Previous
                  </Button>
                  <Button
                    type="button"
                    variant="outline"
                    size="sm"
                    disabled={page >= pageCount || list.isPlaceholderData}
                    onClick={() => setPage((current) => Math.min(pageCount, current + 1))}
                  >
                    Next
                  </Button>
                </div>
              </div>
            ) : null}
          </CardContent>
        </Card>

        <div className="space-y-4">
          <Card className="border-border/70">
            <CardHeader className="gap-3">
              <div className="flex items-center gap-2 text-muted-foreground text-xs uppercase tracking-[0.18em]">
                <GraduationCap className="size-3.5" />
                Class trend
              </div>
              <div className="flex items-center justify-between gap-3">
                <CardTitle className="text-xl">Average across all students</CardTitle>
                <div className="flex flex-wrap items-center gap-2">
                  <Badge variant="outline">{classStudentsIncluded} students</Badge>
                  <Badge variant="outline">{classSolvedQuestions} answers</Badge>
                </div>
              </div>
            </CardHeader>
            <CardContent>
              {summary.isPending ? (
                <TableSkeleton rows={4} />
              ) : summary.isError ? (
                <QueryError error={summary.error} />
              ) : classScoreTrend.length === 0 ? (
                <EmptyState
                  title="No answers yet"
                  hint="This class graph appears after students answer questions."
                />
              ) : (
                <div className="space-y-3">
                  {/* Every answer counts once, so a student who answers more weighs more,
                      and the first points are whoever answered first. */}
                  <p className="text-muted-foreground text-xs">
                    The average score of every answer given so far, in the order they were
                    given.
                  </p>
                  <div className="h-72 w-full">
                    <ResponsiveContainer width="100%" height="100%">
                      <LineChart
                        data={classScoreTrend}
                        margin={{ top: 12, right: 12, left: 24, bottom: 28 }}
                      >
                        <CartesianGrid stroke="currentColor" strokeOpacity={0.08} />
                        {/* x is the running count of answers, unique per point (a day label
                            repeats, and the hover would find only the day's first answer). */}
                        <XAxis
                          dataKey="totalSolved"
                          type="number"
                          domain={["dataMin", "dataMax"]}
                          allowDecimals={false}
                          padding={{ left: 10, right: 10 }}
                          tickLine={false}
                          axisLine={false}
                          minTickGap={24}
                          stroke="currentColor"
                          tick={{ fill: "currentColor", fontSize: 12, opacity: 0.75 }}
                          label={{
                            value: "Answers so far, oldest to newest",
                            position: "insideBottom",
                            offset: -6,
                            fill: "currentColor",
                            fontSize: 12,
                          }}
                        />
                        <YAxis
                          domain={[0, 100]}
                          tickCount={6}
                          tickFormatter={(value: number) => `${value}`}
                          tickLine={false}
                          axisLine={false}
                          stroke="currentColor"
                          tick={{ fill: "currentColor", fontSize: 12, opacity: 0.75 }}
                          label={{
                            value: "Class average",
                            angle: -90,
                            position: "insideLeft",
                            offset: -4,
                            fill: "currentColor",
                            fontSize: 12,
                          }}
                        />
                        <Tooltip
                          contentStyle={{
                            background: "var(--card)",
                            border: "1px solid color-mix(in oklab, var(--border) 80%, transparent)",
                            borderRadius: "12px",
                            color: "var(--card-foreground)",
                          }}
                          formatter={(value) => [
                            scoreLabel(typeof value === "number" ? value : 0),
                            "Class average",
                          ]}
                          labelFormatter={(_label, payload) => {
                            const point = payload?.[0]?.payload;
                            if (!point) return "";
                            const answers = pluralise(point.totalSolved, "answer");
                            const students = pluralise(point.studentsIncluded, "student");
                            return `After ${answers} from ${students} · ${formatDate(point.timestamp, true)}`;
                          }}
                        />
                        <Line
                          type="linear"
                          dataKey="averageScore"
                          name="Class average"
                          stroke="var(--foreground)"
                          strokeWidth={2.5}
                          // Past ~40 answers the dots merge into a bar; the hover still marks one.
                          dot={
                            classScoreTrend.length > 40 ? false : { r: 3, fill: "var(--foreground)" }
                          }
                          activeDot={{ r: 5 }}
                        />
                      </LineChart>
                    </ResponsiveContainer>
                  </div>
                </div>
              )}
            </CardContent>
          </Card>

          <ClassWeaknessCard
            curriculumVersionId={curriculumVersionId}
            onSelectStudent={setSelectedStudentId}
          />

          <Card className="border-border/70">
            <CardHeader className="gap-3">
              <div className="flex items-center gap-2 text-muted-foreground text-xs uppercase tracking-[0.18em]">
                <GraduationCap className="size-3.5" />
                Learner detail
              </div>
              <CardTitle className="text-xl">
                {selectedStudent?.display_name ?? "Choose a learner"}
              </CardTitle>
            </CardHeader>
            <CardContent className="space-y-4">
              {selectedStudentId === null ? (
                <EmptyState
                  title="No learner selected"
                  hint="Choose a learner from the roster to inspect score trends, mastery, and session history."
                />
              ) : (
                <div className="grid gap-3 sm:grid-cols-3">
                  <div className="rounded-xl border border-border/70 bg-muted/30 p-3">
                    <div className="text-muted-foreground text-xs uppercase tracking-[0.14em]">
                      Answered
                    </div>
                    <div className="mt-2 font-semibold text-lg">
                      {progress.data?.answered ?? "—"}
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
                      Total sessions
                    </div>
                    <div className="mt-2 font-semibold text-lg">{totalSessions}</div>
                  </div>
                </div>
              )}
            </CardContent>
          </Card>

          {progress.isPending && selectedStudentId !== null ? <TableSkeleton rows={6} /> : null}
          {progress.isError ? <QueryError error={progress.error} /> : null}

          {progress.data ? (
            <div className="space-y-4">
              <Card className="border-border/70">
                <CardHeader>
                  <div className="flex items-center justify-between gap-3">
                    <CardTitle className="text-base">Scores over time</CardTitle>
                    <Badge variant="outline">{scoreTrend.length} attempts</Badge>
                  </div>
                  <CardDescription>
                    Raw question scores and the running average, shown together from oldest to
                    newest.
                  </CardDescription>
                </CardHeader>
                <CardContent>
                  {scoreTrend.length === 0 ? (
                    <EmptyState
                      title="No scored attempts yet"
                      hint="The score graph appears after this learner answers at least one question."
                    />
                  ) : (
                    <div className="space-y-3">
                      <div className="flex flex-wrap gap-4 text-muted-foreground text-xs">
                        <span className="inline-flex items-center gap-2">
                          <span className="h-2.5 w-2.5 rounded-full bg-primary" />
                          Question score
                        </span>
                        <span className="inline-flex items-center gap-2">
                          <span className="h-2.5 w-2.5 rounded-full bg-foreground" />
                          Running average
                        </span>
                      </div>
                      <div className="h-80 w-full">
                        <ResponsiveContainer width="100%" height="100%">
                          <LineChart
                            data={scoreTrend}
                            margin={{ top: 12, right: 12, left: 24, bottom: 28 }}
                          >
                            <CartesianGrid stroke="currentColor" strokeOpacity={0.08} />
                            {/* x is the attempt's place in the learner's history: unique per
                                point, so hovering finds that point (a day label repeats). */}
                            <XAxis
                              dataKey="sequence"
                              type="number"
                              domain={["dataMin", "dataMax"]}
                              allowDecimals={false}
                              padding={{ left: 10, right: 10 }}
                              tickLine={false}
                              axisLine={false}
                              minTickGap={24}
                              stroke="currentColor"
                              tick={{ fill: "currentColor", fontSize: 12, opacity: 0.75 }}
                              label={{
                                value: "Attempt, oldest to newest",
                                position: "insideBottom",
                                offset: -6,
                                fill: "currentColor",
                                fontSize: 12,
                              }}
                            />
                            <YAxis
                              domain={[0, 100]}
                              tickCount={6}
                              tickFormatter={(value: number) => `${value}`}
                              tickLine={false}
                              axisLine={false}
                              stroke="currentColor"
                              tick={{ fill: "currentColor", fontSize: 12, opacity: 0.75 }}
                              label={{
                                value: "Score",
                                angle: -90,
                                position: "insideLeft",
                                offset: -4,
                                fill: "currentColor",
                                fontSize: 12,
                              }}
                            />
                            <Tooltip
                              contentStyle={{
                                background: "var(--card)",
                                border:
                                  "1px solid color-mix(in oklab, var(--border) 80%, transparent)",
                                borderRadius: "12px",
                                color: "var(--card-foreground)",
                              }}
                              formatter={(value, name) => [
                                scoreLabel(typeof value === "number" ? value : 0),
                                name === "averageScore" ? "Running average" : "Question score",
                              ]}
                              labelFormatter={(_label, payload) => {
                                const point = payload?.[0]?.payload;
                                if (!point) return "";
                                return chartLabel(point.timestamp, point.sequence, scoreTrend.length);
                              }}
                            />
                            {/* Straight segments: a curve between a 0 and a 100 passes through
                                scores no attempt had, and overshoots the 0–100 range. */}
                            <Line
                              type="linear"
                              dataKey="score"
                              stroke="var(--primary)"
                              strokeWidth={2.5}
                              dot={{ r: 3, fill: "var(--primary)" }}
                              activeDot={{ r: 5 }}
                            />
                            <Line
                              type="linear"
                              dataKey="averageScore"
                              stroke="var(--foreground)"
                              strokeWidth={2.5}
                              dot={{ r: 3, fill: "var(--foreground)" }}
                              activeDot={{ r: 5 }}
                            />
                          </LineChart>
                        </ResponsiveContainer>
                      </div>
                    </div>
                  )}
                </CardContent>
              </Card>

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
                            {(() => {
                              const styles = topicBandStyles(topic.band);
                              return (
                                <>
                                  <div className="flex items-center justify-between gap-2">
                                    <div>
                                      <div className="font-medium">{topic.topic_name}</div>
                                      <div className="text-muted-foreground text-xs">
                                        Next difficulty: {topic.next_difficulty} ·{" "}
                                        {topic.observations} score(s)
                                      </div>
                                    </div>
                                    <Badge
                                      variant="outline"
                                      className={styles.badgeClassName}
                                    >
                                      {topic.band}
                                    </Badge>
                                  </div>
                                  <Progress
                                    value={masteryPercent(topic.p_known)}
                                    indicatorClassName={styles.progressClassName}
                                  />
                                </>
                              );
                            })()}
                          </div>
                        ))}
                      </div>
                    )}
                  </CardContent>
                </Card>

                <Card className="border-border/70">
                  <CardHeader>
                    <CardTitle className="text-base">Training sessions</CardTitle>
                  </CardHeader>
                  <CardContent>
                    {progress.data.sessions.length === 0 ? (
                      <EmptyState
                        title="No training sessions yet"
                        hint="Sessions appear here after a learner joins from the classroom link."
                      />
                    ) : (
                      <Table>
                        <TableHeader>
                          <TableRow>
                            <TableHead>Session</TableHead>
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
                                    <Link
                                      href={`/students/join/session/${session.id}` as Route}
                                    >
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
            </div>
          ) : null}
        </div>
      </div>
    </>
  );
}
