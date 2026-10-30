"use client";

/**
 * The three learning charts, on whichever dataset is picked. Everything is computed in the
 * browser by `learning-analysis.ts`; a point under `MIN_N` answers is drawn hollow and kept out
 * of the shaded interval, so a thin point never reads as a trend.
 */

import { useMemo, useState } from "react";
import {
  Area,
  Bar,
  BarChart,
  CartesianGrid,
  Cell,
  ComposedChart,
  ErrorBar,
  Line,
  LineChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import { Badge } from "@/components/ui/badge";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Tabs, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { CS189_SNAPSHOT } from "./cs189-snapshot";
import {
  type Answer,
  byDifficulty,
  byDifficultyAndAnswer,
  byDifficultyOverTime,
  bySubtopicsExplored,
  type DifficultyScore,
  type FirstLatest,
  firstVsLatest,
  learningCurve,
  MIN_N,
  type Rate,
  type TimeBucket,
} from "./learning-analysis";
import { MOCK_CLASS } from "./mock-learning";

const DATASETS = {
  mock: {
    label: "Simulated class",
    note: "36 simulated students who do learn (mock data). This is what the charts look like when the evidence is there.",
    answers: MOCK_CLASS,
  },
  cs189: {
    label: "CS189 today",
    note: "CS189's 64 scored answers from 24 students, copied from the dev database on Oct 25. Most are test runs.",
    answers: CS189_SNAPSHOT,
  },
} satisfies Record<string, { label: string; note: string; answers: Answer[] }>;

type DatasetKey = keyof typeof DATASETS;

const DIFFICULTY_COLORS = {
  easy: "var(--chart-1)",
  medium: "var(--chart-2)",
  hard: "var(--chart-4)",
};

const TOOLTIP_STYLE = {
  background: "var(--card)",
  border: "1px solid color-mix(in oklab, var(--border) 80%, transparent)",
  borderRadius: "12px",
  color: "var(--card-foreground)",
  fontSize: 12,
};

const AXIS_TICK = { fill: "currentColor", fontSize: 12, opacity: 0.75 };

function pct(value: number | null) {
  return value === null ? "—" : `${Math.round(value)}%`;
}

function rateText(rate: Rate) {
  if (rate.n === 0) return "no answers";
  const interval = rate.enough ? `, 95% CI ${pct(rate.low)}–${pct(rate.high)}` : ", too few to read";
  return `${pct(rate.rate)} of ${rate.n}${interval}`;
}

/** Filled when the point has `MIN_N` answers, hollow when it does not. */
function RateDot({
  cx,
  cy,
  color,
  enough,
}: {
  cx?: number;
  cy?: number;
  color: string;
  enough: boolean;
}) {
  if (cx === undefined || cy === undefined) return null;
  return (
    <circle
      cx={cx}
      cy={cy}
      r={4}
      fill={enough ? color : "var(--card)"}
      stroke={color}
      strokeWidth={2}
    />
  );
}

function ChartNote({
  reads,
  caveat,
  readsLabel = "Reads as learning when",
}: {
  reads: string;
  caveat: string;
  readsLabel?: string;
}) {
  return (
    <dl className="grid gap-2 text-sm md:grid-cols-2">
      <div>
        <dt className="font-medium">{readsLabel}</dt>
        <dd className="text-muted-foreground">{reads}</dd>
      </div>
      <div>
        <dt className="font-medium">What it cannot show</dt>
        <dd className="text-muted-foreground">{caveat}</dd>
      </div>
    </dl>
  );
}

function ExploredCard({ answers }: { answers: Answer[] }) {
  const points = useMemo(() => bySubtopicsExplored(answers), [answers]);
  const data = points.map((point) => ({
    explored: point.explored,
    score: point.rate,
    band: point.enough ? [point.low, point.high] : null,
    point,
  }));
  return (
    <Card>
      <CardHeader>
        <CardTitle>Subtopics explored against average score</CardTitle>
        <CardDescription>
          Average score of the answers students gave once they had reached 1, 2, 3… different
          subtopics.
        </CardDescription>
      </CardHeader>
      <CardContent className="space-y-4">
        <div className="h-64 w-full">
          <ResponsiveContainer width="100%" height="100%">
            <ComposedChart data={data} margin={{ top: 8, right: 12, left: 0, bottom: 20 }}>
              <CartesianGrid stroke="currentColor" strokeOpacity={0.08} />
              <XAxis
                dataKey="explored"
                tickLine={false}
                axisLine={false}
                tick={AXIS_TICK}
                label={{
                  value: "Subtopics explored so far",
                  position: "insideBottom",
                  offset: -10,
                  fill: "currentColor",
                  fontSize: 12,
                }}
              />
              <YAxis
                domain={[0, 100]}
                tickFormatter={(value: number) => `${value}%`}
                tickLine={false}
                axisLine={false}
                tick={AXIS_TICK}
                width={48}
              />
              <Tooltip
                contentStyle={TOOLTIP_STYLE}
                labelFormatter={(label) => `${label} subtopic${label === 1 ? "" : "s"} explored`}
                formatter={(_value, name, item) => {
                  if (name === "band") return [null, null];
                  const point = item.payload.point;
                  return [
                    `${rateText(point)} · ${point.students} student${point.students === 1 ? "" : "s"}`,
                    "Average score",
                  ];
                }}
              />
              <Area
                dataKey="band"
                stroke="none"
                fill="var(--primary)"
                fillOpacity={0.12}
                isAnimationActive={false}
                legendType="none"
                activeDot={false}
              />
              <Line
                type="linear"
                dataKey="score"
                stroke="var(--primary)"
                strokeWidth={2.5}
                isAnimationActive={false}
                dot={(props) => (
                  <RateDot
                    key={`x-${props.index}`}
                    cx={props.cx}
                    cy={props.cy}
                    color="var(--primary)"
                    enough={props.payload.point.enough}
                  />
                )}
              />
            </ComposedChart>
          </ResponsiveContainer>
        </div>
        <ChartNote
          reads="the score holds or rises while students move on to new subtopics: they reach new material without falling behind on it."
          caveat="learning by itself. Later subtopics are different, often harder material, and only the students who got that far are in the later points."
        />
      </CardContent>
    </Card>
  );
}

/**
 * The hover panel of one difficulty bar: the score large, what it rests on in words, and its 95%
 * interval drawn on a 0–100% track, so how sure the number is reads at a glance.
 */
function DifficultyTooltip({ row }: { row: DifficultyScore }) {
  const color = DIFFICULTY_COLORS[row.difficulty];
  const level = row.difficulty.replace(/^./, (c) => c.toUpperCase());
  return (
    <div className="w-60 space-y-3 rounded-xl border border-border/80 bg-card p-3.5 text-card-foreground shadow-lg">
      <div className="flex items-center gap-2 font-medium text-sm">
        <span className="size-2.5 rounded-full" style={{ background: color }} />
        {level} questions
      </div>
      {row.n === 0 ? (
        <p className="text-muted-foreground text-sm">No answers at this level yet.</p>
      ) : (
        <>
          <div>
            <p className="font-semibold text-3xl tabular-nums leading-none">{pct(row.rate)}</p>
            <p className="mt-1 text-muted-foreground text-xs">
              {row.correct} of {row.n} answer{row.n === 1 ? "" : "s"} right
            </p>
          </div>
          {row.enough && row.low !== null && row.high !== null ? (
            <div className="space-y-1.5">
              <div className="relative h-2 rounded-full bg-muted" aria-hidden="true">
                <div
                  className="absolute inset-y-0 rounded-full opacity-60"
                  style={{
                    left: `${row.low}%`,
                    width: `${row.high - row.low}%`,
                    background: color,
                  }}
                />
                <div
                  className="absolute top-1/2 h-3.5 w-0.5 -translate-x-1/2 -translate-y-1/2 rounded-full bg-foreground"
                  style={{ left: `${row.rate ?? 0}%` }}
                />
              </div>
              <p className="text-muted-foreground text-xs">
                Likely between {pct(row.low)} and {pct(row.high)} (95% interval)
              </p>
            </div>
          ) : (
            <p className="rounded-md bg-muted px-2 py-1.5 text-muted-foreground text-xs">
              Only {row.n} answer{row.n === 1 ? "" : "s"}: too few to read. Wait for at least{" "}
              {MIN_N}.
            </p>
          )}
          <p className="border-border/70 border-t pt-2 text-muted-foreground text-xs">
            From {row.students} student{row.students === 1 ? "" : "s"}
          </p>
        </>
      )}
    </div>
  );
}

function DifficultyScoreCard({ answers }: { answers: Answer[] }) {
  const rows = useMemo(() => byDifficulty(answers), [answers]);
  const data = rows.map((row) => ({
    // The count rides on the axis label, clear of the bar's interval whisker.
    label: `${row.difficulty.replace(/^./, (c) => c.toUpperCase())} · n=${row.n}`,
    score: row.rate,
    // ErrorBar draws distances below and above the bar, only for points with enough answers.
    error:
      row.enough && row.rate !== null && row.low !== null && row.high !== null
        ? [row.rate - row.low, row.high - row.rate]
        : [0, 0],
    row,
  }));
  return (
    <Card>
      <CardHeader>
        <CardTitle>Difficulty against average score</CardTitle>
        <CardDescription>
          Average score on easy, medium and hard questions, over every answer.
        </CardDescription>
      </CardHeader>
      <CardContent className="space-y-4">
        <div className="h-64 w-full">
          <ResponsiveContainer width="100%" height="100%">
            <BarChart data={data} margin={{ top: 8, right: 12, left: 0, bottom: 20 }}>
              <CartesianGrid stroke="currentColor" strokeOpacity={0.08} vertical={false} />
              <XAxis
                dataKey="label"
                tickLine={false}
                axisLine={false}
                tick={AXIS_TICK}
                label={{
                  value: "Served difficulty",
                  position: "insideBottom",
                  offset: -10,
                  fill: "currentColor",
                  fontSize: 12,
                }}
              />
              <YAxis
                domain={[0, 100]}
                tickFormatter={(value: number) => `${value}%`}
                tickLine={false}
                axisLine={false}
                tick={AXIS_TICK}
                width={48}
              />
              <Tooltip
                cursor={{ fill: "currentColor", fillOpacity: 0.04 }}
                wrapperStyle={{ outline: "none" }}
                content={({ active, payload }) =>
                  active && payload?.[0] ? (
                    <DifficultyTooltip row={payload[0].payload.row as DifficultyScore} />
                  ) : null
                }
              />
              {/* minPointSize: a level scoring 0% still shows a sliver and its n. */}
              <Bar
                dataKey="score"
                radius={[6, 6, 0, 0]}
                maxBarSize={72}
                minPointSize={3}
                isAnimationActive={false}
              >
                {data.map((entry) => {
                  const color = DIFFICULTY_COLORS[entry.row.difficulty];
                  return (
                    <Cell
                      key={entry.label}
                      fill={color}
                      fillOpacity={entry.row.enough ? 0.85 : 0.2}
                      stroke={color}
                      strokeWidth={entry.row.enough ? 0 : 2}
                    />
                  );
                })}
                <ErrorBar dataKey="error" width={10} strokeWidth={1.5} stroke="var(--foreground)" />
              </Bar>
            </BarChart>
          </ResponsiveContainer>
        </div>
        <ChartNote
          readsLabel="What it can show"
          reads="how each served level went, and whether students reached medium and hard at all. A data check, not evidence of learning."
          caveat="whether the labels are right. The tutor serves hard questions only to students doing well, so stronger students fill the hard bar and it can outscore easy (the simulated class does exactly that). Judging difficulty fairly needs item response theory, which estimates question difficulty and student ability together. Pale bars rest on fewer than 5 answers."
        />
      </CardContent>
    </Card>
  );
}

const LEVELS = ["easy", "medium", "hard"] as const;

function periodLabel(bucket: TimeBucket, long = false) {
  const date = new Date(`${bucket.start}T00:00:00Z`);
  const format = new Intl.DateTimeFormat(undefined, {
    month: "short",
    day: "numeric",
    timeZone: "UTC",
    ...(long && bucket.unit === "day" ? { weekday: "short" } : {}),
  }).format(date);
  return bucket.unit === "week" && long ? `Week of ${format}` : format;
}

/** The hover panel of one period: every level's score, and what it rests on. */
function OverTimeTooltip({ bucket }: { bucket: TimeBucket }) {
  return (
    <div className="w-64 space-y-3 rounded-xl border border-border/80 bg-card p-3.5 text-card-foreground shadow-lg">
      <div className="flex items-baseline justify-between gap-2">
        <p className="font-medium text-sm">{periodLabel(bucket, true)}</p>
        <p className="text-muted-foreground text-xs">
          {bucket.total} answer{bucket.total === 1 ? "" : "s"}
        </p>
      </div>
      {bucket.total === 0 ? (
        <p className="text-muted-foreground text-sm">No answers in this period.</p>
      ) : (
        <ul className="space-y-2">
          {LEVELS.map((level) => {
            const rate = bucket[level];
            return (
              <li key={level} className="flex items-center gap-2.5">
                <span
                  className="size-2.5 shrink-0 rounded-full"
                  style={{ background: DIFFICULTY_COLORS[level] }}
                />
                <span className="w-16 text-sm capitalize">{level}</span>
                {rate.n === 0 ? (
                  <span className="text-muted-foreground text-xs">not served</span>
                ) : (
                  <>
                    <span
                      className={`w-11 text-right font-semibold tabular-nums ${rate.enough ? "" : "text-muted-foreground"}`}
                    >
                      {pct(rate.rate)}
                    </span>
                    <span className="text-muted-foreground text-xs">
                      {rate.correct}/{rate.n}
                      {rate.enough ? "" : " · too few"}
                    </span>
                  </>
                )}
              </li>
            );
          })}
        </ul>
      )}
    </div>
  );
}

function OverTimeCard({ answers }: { answers: Answer[] }) {
  const buckets = useMemo(() => byDifficultyOverTime(answers), [answers]);
  if (buckets.length === 0) return null;
  const busiest = Math.max(...buckets.map((bucket) => bucket.total), 1);
  const data = buckets.map((bucket) => ({
    label: periodLabel(bucket),
    easy: bucket.easy.rate,
    medium: bucket.medium.rate,
    hard: bucket.hard.rate,
    easyCount: bucket.easy.n,
    mediumCount: bucket.medium.n,
    hardCount: bucket.hard.n,
    bucket,
  }));
  return (
    <Card>
      <CardHeader>
        <CardTitle>Easy, medium and hard over time</CardTitle>
        <CardDescription>
          Each line is the share correct at one difficulty per {buckets[0].unit}. The pale bars
          underneath are how many questions of each level were answered that {buckets[0].unit}.
        </CardDescription>
      </CardHeader>
      <CardContent className="space-y-4">
        <div className="flex flex-wrap gap-4 text-muted-foreground text-xs">
          {LEVELS.map((level) => (
            <span key={level} className="inline-flex items-center gap-2 capitalize">
              <span className="h-0.5 w-4" style={{ background: DIFFICULTY_COLORS[level] }} />
              {level}
            </span>
          ))}
          <span className="inline-flex items-center gap-2">
            <span className="h-3 w-2 rounded-sm bg-muted-foreground/25" />
            Questions answered
          </span>
        </div>
        <div className="h-80 w-full">
          <ResponsiveContainer width="100%" height="100%">
            <ComposedChart data={data} margin={{ top: 8, right: 12, left: 0, bottom: 20 }}>
              <CartesianGrid stroke="currentColor" strokeOpacity={0.08} vertical={false} />
              <XAxis
                dataKey="label"
                tickLine={false}
                axisLine={false}
                tick={AXIS_TICK}
                minTickGap={16}
                label={{
                  value: buckets[0].unit === "day" ? "Day" : "Week",
                  position: "insideBottom",
                  offset: -10,
                  fill: "currentColor",
                  fontSize: 12,
                }}
              />
              <YAxis
                yAxisId="score"
                domain={[0, 100]}
                tickFormatter={(value: number) => `${value}%`}
                tickLine={false}
                axisLine={false}
                tick={AXIS_TICK}
                width={48}
              />
              {/* Counts sit in the bottom third: the axis runs to three times the busiest. */}
              <YAxis yAxisId="count" orientation="right" hide domain={[0, busiest * 3]} />
              <Tooltip
                cursor={{ fill: "currentColor", fillOpacity: 0.04 }}
                wrapperStyle={{ outline: "none" }}
                content={({ active, payload }) =>
                  active && payload?.[0] ? (
                    <OverTimeTooltip bucket={payload[0].payload.bucket as TimeBucket} />
                  ) : null
                }
              />
              {LEVELS.map((level, index) => (
                <Bar
                  key={`${level}-count`}
                  yAxisId="count"
                  dataKey={`${level}Count`}
                  stackId="count"
                  fill={DIFFICULTY_COLORS[level]}
                  fillOpacity={0.25}
                  maxBarSize={28}
                  radius={index === LEVELS.length - 1 ? [3, 3, 0, 0] : 0}
                  isAnimationActive={false}
                />
              ))}
              {LEVELS.map((level) => (
                <Line
                  key={level}
                  yAxisId="score"
                  type="linear"
                  dataKey={level}
                  stroke={DIFFICULTY_COLORS[level]}
                  strokeWidth={2.5}
                  connectNulls={false}
                  isAnimationActive={false}
                  dot={(props) => (
                    <RateDot
                      key={`${level}-t-${props.index}`}
                      cx={props.cx}
                      cy={props.cy}
                      color={DIFFICULTY_COLORS[level]}
                      enough={props.payload.bucket[level].enough}
                    />
                  )}
                />
              ))}
            </ComposedChart>
          </ResponsiveContainer>
        </div>
        <ChartNote
          reads="a line rises over the weeks while the bars shift from easy towards hard: students get more right at a level while being served harder questions."
          caveat="learning by itself: each period may cover new subtopics, and who practised that period changes. Hollow dots rest on fewer than 5 answers; a line skips periods its level was not served."
        />
      </CardContent>
    </Card>
  );
}

function LearningCurveCard({ answers, k }: { answers: Answer[]; k: number }) {
  const { everyone, cohort, cohortSize } = useMemo(() => learningCurve(answers, k), [answers, k]);
  const data = everyone.map((point) => {
    const fixed = cohort.find((each) => each.opportunity === point.opportunity);
    return {
      opportunity: point.opportunity,
      everyone: point.rate,
      everyoneRate: point,
      cohort: fixed?.rate ?? null,
      cohortRate: fixed ?? null,
      band: fixed?.enough ? [fixed.low, fixed.high] : null,
    };
  });
  return (
    <Card>
      <CardHeader>
        <div className="flex flex-wrap items-center justify-between gap-2">
          <CardTitle>Learning curve</CardTitle>
          <Badge variant="outline">
            {cohortSize} student–subtopic pair{cohortSize === 1 ? "" : "s"} with {k}+ answers
          </Badge>
        </div>
        <CardDescription>
          Share correct on a student's 1st, 2nd, 3rd… answer on the same subtopic.
        </CardDescription>
      </CardHeader>
      <CardContent className="space-y-4">
        <div className="flex flex-wrap gap-4 text-muted-foreground text-xs">
          <span className="inline-flex items-center gap-2">
            <span className="h-0.5 w-5 bg-primary" />
            Same students throughout ({k}+ answers), with 95% interval
          </span>
          <span className="inline-flex items-center gap-2">
            <span className="h-0 w-5 border-muted-foreground border-t-2 border-dashed" />
            Everyone who reached that answer
          </span>
        </div>
        <div className="h-72 w-full">
          <ResponsiveContainer width="100%" height="100%">
            <ComposedChart data={data} margin={{ top: 8, right: 12, left: 0, bottom: 20 }}>
              <CartesianGrid stroke="currentColor" strokeOpacity={0.08} />
              <XAxis
                dataKey="opportunity"
                tickLine={false}
                axisLine={false}
                tick={AXIS_TICK}
                label={{
                  value: "Answer number on the subtopic",
                  position: "insideBottom",
                  offset: -10,
                  fill: "currentColor",
                  fontSize: 12,
                }}
              />
              <YAxis
                domain={[0, 100]}
                tickFormatter={(value: number) => `${value}%`}
                tickLine={false}
                axisLine={false}
                tick={AXIS_TICK}
                width={48}
              />
              <Tooltip
                contentStyle={TOOLTIP_STYLE}
                labelFormatter={(label) => `Answer ${label} on a subtopic`}
                formatter={(_value, name, item) => {
                  const point = item.payload;
                  if (name === "band") return [null, null];
                  return name === "cohort"
                    ? [point.cohortRate ? rateText(point.cohortRate) : "—", "Same students"]
                    : [rateText(point.everyoneRate), "Everyone"];
                }}
              />
              <Area
                dataKey="band"
                stroke="none"
                fill="var(--primary)"
                fillOpacity={0.12}
                isAnimationActive={false}
                connectNulls={false}
                legendType="none"
                activeDot={false}
              />
              <Line
                type="linear"
                dataKey="everyone"
                stroke="var(--muted-foreground)"
                strokeDasharray="5 4"
                strokeWidth={1.5}
                dot={(props) => (
                  <RateDot
                    key={`e-${props.index}`}
                    cx={props.cx}
                    cy={props.cy}
                    color="var(--muted-foreground)"
                    enough={props.payload.everyoneRate.enough}
                  />
                )}
                isAnimationActive={false}
              />
              <Line
                type="linear"
                dataKey="cohort"
                stroke="var(--primary)"
                strokeWidth={2.5}
                connectNulls={false}
                dot={(props) => (
                  <RateDot
                    key={`c-${props.index}`}
                    cx={props.cx}
                    cy={props.cy}
                    color="var(--primary)"
                    enough={props.payload.cohortRate?.enough ?? false}
                  />
                )}
                isAnimationActive={false}
              />
            </ComposedChart>
          </ResponsiveContainer>
        </div>
        <ChartNote
          reads="the solid line rises (fewer errors with practice) and its shaded interval clears the first answer's."
          caveat="why they improved, or how the quick learners did: the solid line is only the students who needed that many answers. Questions also get harder as students do well, which pulls it down; the chart by difficulty below separates that out."
        />
      </CardContent>
    </Card>
  );
}

function Dumbbell({ row }: { row: FirstLatest }) {
  const first = row.first.rate ?? 0;
  const latest = row.latest.rate ?? 0;
  const thin = !row.first.enough;
  const up = latest >= first;
  return (
    <li className="grid grid-cols-1 gap-1 sm:grid-cols-[minmax(0,14rem)_1fr_7rem] sm:items-center sm:gap-4">
      <span className="truncate font-medium text-sm" title={row.subtopic}>
        {row.subtopic}
      </span>
      <div className="relative h-6" aria-hidden="true">
        <div className="absolute inset-x-0 top-1/2 h-px bg-border" />
        <div
          className={`absolute top-1/2 h-1 -translate-y-1/2 rounded-full ${up ? "bg-primary/60" : "bg-destructive/60"}`}
          style={{ left: `${Math.min(first, latest)}%`, width: `${Math.abs(latest - first)}%` }}
        />
        <span
          className="absolute top-1/2 size-3 -translate-x-1/2 -translate-y-1/2 rounded-full border-2 border-muted-foreground bg-card"
          style={{ left: `${first}%` }}
        />
        <span
          className={`absolute top-1/2 size-3 -translate-x-1/2 -translate-y-1/2 rounded-full border-2 ${up ? "border-primary" : "border-destructive"} ${thin ? "bg-card" : up ? "bg-primary" : "bg-destructive"}`}
          style={{ left: `${latest}%` }}
        />
      </div>
      <span className="text-muted-foreground text-xs tabular-nums">
        {pct(first)} → {pct(latest)} · n={row.first.n}
        {thin ? " (thin)" : ""}
      </span>
      <span className="sr-only">
        First answers {rateText(row.first)}; latest answers {rateText(row.latest)}. Improved{" "}
        {row.improved}, same {row.same}, worse {row.worse}.
      </span>
    </li>
  );
}

function FirstVsLatestCard({ answers }: { answers: Answer[] }) {
  const rows = useMemo(() => firstVsLatest(answers), [answers]);
  const [all, ...subtopics] = rows;
  const total = all.improved + all.same + all.worse;
  return (
    <Card>
      <CardHeader>
        <CardTitle>First answer against latest, per subtopic</CardTitle>
        <CardDescription>
          For every student who answered a subtopic at least twice: was their first answer right,
          and is their latest?
        </CardDescription>
      </CardHeader>
      <CardContent className="space-y-5">
        {total === 0 ? (
          <p className="text-muted-foreground text-sm">
            No student has answered a subtopic twice yet.
          </p>
        ) : (
          <>
            <div className="space-y-2">
              <div className="flex h-3 overflow-hidden rounded-full bg-muted" aria-hidden="true">
                <div className="bg-primary" style={{ width: `${(100 * all.improved) / total}%` }} />
                <div
                  className="bg-muted-foreground/40"
                  style={{ width: `${(100 * all.same) / total}%` }}
                />
                <div className="bg-destructive" style={{ width: `${(100 * all.worse) / total}%` }} />
              </div>
              <p className="text-sm">
                <span className="font-medium text-primary">{all.improved} improved</span> ·{" "}
                {all.same} unchanged ·{" "}
                <span className="font-medium text-destructive">{all.worse} got worse</span>{" "}
                <span className="text-muted-foreground">of {total} student–subtopic pairs</span>
              </p>
            </div>
            <ul className="space-y-3">
              <Dumbbell row={all} />
              {subtopics.map((row) => (
                <Dumbbell key={row.subtopic} row={row} />
              ))}
            </ul>
            <p className="text-muted-foreground text-xs">
              Hollow dot: first answers. Filled dot: latest answers, hollow when fewer than {MIN_N}
              {" "}students. The scale runs 0–100% correct.
            </p>
          </>
        )}
        <ChartNote
          reads="most pairs improved and few got worse, on most subtopics rather than one. Read it beside the learning curve, never alone."
          caveat="learning on its own: the tutor stops serving a subtopic after right answers, so the latest answer leans right even with no learning. Students who answered once are left out."
        />
      </CardContent>
    </Card>
  );
}

function DifficultyCard({ answers }: { answers: Answer[] }) {
  const rows = useMemo(() => byDifficultyAndAnswer(answers), [answers]);
  const data = rows.map((row) => ({
    label: row.label,
    easy: row.easy.rate,
    medium: row.medium.rate,
    hard: row.hard.rate,
    rates: row,
  }));
  return (
    <Card>
      <CardHeader>
        <CardTitle>Learning curve at each difficulty</CardTitle>
        <CardDescription>
          Share correct on easy, medium and hard questions, by answer number on the subtopic. Each
          line compares like with like, so harder questions earned by doing well do not read as
          forgetting.
        </CardDescription>
      </CardHeader>
      <CardContent className="space-y-4">
        <div className="flex flex-wrap gap-4 text-muted-foreground text-xs">
          {(["easy", "medium", "hard"] as const).map((level) => (
            <span key={level} className="inline-flex items-center gap-2 capitalize">
              <span
                className="h-2.5 w-2.5 rounded-full"
                style={{ background: DIFFICULTY_COLORS[level] }}
              />
              {level}
            </span>
          ))}
        </div>
        <div className="h-64 w-full">
          <ResponsiveContainer width="100%" height="100%">
            <LineChart data={data} margin={{ top: 8, right: 12, left: 0, bottom: 20 }}>
              <CartesianGrid stroke="currentColor" strokeOpacity={0.08} />
              <XAxis
                dataKey="label"
                tickLine={false}
                axisLine={false}
                tick={AXIS_TICK}
                label={{
                  value: "Answer number on the subtopic",
                  position: "insideBottom",
                  offset: -10,
                  fill: "currentColor",
                  fontSize: 12,
                }}
              />
              <YAxis
                domain={[0, 100]}
                tickFormatter={(value: number) => `${value}%`}
                tickLine={false}
                axisLine={false}
                tick={AXIS_TICK}
                width={48}
              />
              <Tooltip
                contentStyle={TOOLTIP_STYLE}
                labelFormatter={(label) => `Answer ${label} on a subtopic`}
                formatter={(_value, name, item) => [
                  rateText(item.payload.rates[name as "easy" | "medium" | "hard"]),
                  String(name).replace(/^./, (c) => c.toUpperCase()),
                ]}
              />
              {(["easy", "medium", "hard"] as const).map((level) => (
                <Line
                  key={level}
                  type="linear"
                  dataKey={level}
                  stroke={DIFFICULTY_COLORS[level]}
                  strokeWidth={2.5}
                  connectNulls={false}
                  isAnimationActive={false}
                  dot={(props) => (
                    <RateDot
                      key={`${level}-${props.index}`}
                      cx={props.cx}
                      cy={props.cy}
                      color={DIFFICULTY_COLORS[level]}
                      enough={props.payload.rates[level].enough}
                    />
                  )}
                />
              ))}
            </LineChart>
          </ResponsiveContainer>
        </div>
        <ChartNote
          reads="each line rises: at the same difficulty, later answers are right more often."
          caveat="learning on a level few students reach; a line with hollow dots is too thin to read."
        />
      </CardContent>
    </Card>
  );
}

export function LearningChartsExperience() {
  const [dataset, setDataset] = useState<DatasetKey>("mock");
  const [k, setK] = useState(4);
  const { answers, note } = DATASETS[dataset];
  return (
    <main className="mx-auto w-full max-w-5xl space-y-6 px-4 py-8 sm:px-6">
      <header className="space-y-3">
        <div className="flex flex-wrap items-center gap-2">
          <Badge variant="outline">Design prototype</Badge>
          <Badge variant="outline">{answers.length} answers</Badge>
        </div>
        <h1 className="font-semibold text-2xl">Is the class learning?</h1>
        <p className="max-w-3xl text-muted-foreground text-sm">
          Charts that can show learning without being built to go up. Every point says how
          many answers it rests on; a point with fewer than {MIN_N} is drawn hollow and never
          shaded as an interval.
        </p>
        <div className="flex flex-wrap items-center gap-3">
          <Tabs value={dataset} onValueChange={(value) => setDataset(value as DatasetKey)}>
            <TabsList>
              {(Object.keys(DATASETS) as DatasetKey[]).map((key) => (
                <TabsTrigger key={key} value={key}>
                  {DATASETS[key].label}
                </TabsTrigger>
              ))}
            </TabsList>
          </Tabs>
          <label className="inline-flex items-center gap-2 text-sm">
            Fixed cohort: students with
            <select
              value={k}
              onChange={(event) => setK(Number(event.target.value))}
              className="h-8 rounded-md border bg-background px-2"
            >
              {[3, 4, 5].map((value) => (
                <option key={value} value={value}>
                  {value}+
                </option>
              ))}
            </select>
            answers on a subtopic
          </label>
        </div>
        <p className="text-muted-foreground text-xs">{note}</p>
      </header>

      <ExploredCard answers={answers} />
      <DifficultyScoreCard answers={answers} />
      <OverTimeCard answers={answers} />
      <LearningCurveCard answers={answers} k={k} />
      <FirstVsLatestCard answers={answers} />
      <DifficultyCard answers={answers} />
    </main>
  );
}
