"use client";

/**
 * The difficulty and topic-alignment judges, one card each, backed by
 * `GET /api/judge-prompts`. Issues and generatability still come back from that
 * list; this screen does not show them.
 *
 * A built-in judge is changed by rewriting its system prompt (ADR-038). Saving
 * re-names the panel, so the rubric version the panel currently answers under
 * is shown against the version it shipped with. Custom rules for the approved
 * taxonomy sit under the two cards.
 *
 * `GET /api/judge-prompts/stats` adds how often the professor agreed with each
 * judge under the current panel, how close the next automatic rewrite is, and
 * which styles have earned trust (skip review) and what each still lacks.
 */

import { Gavel, Scale, Sparkles, TrendingUp, Undo2 } from "lucide-react";
import { useId, useState } from "react";
import { toast } from "sonner";
import { CustomRules } from "@/app/courses/[courseId]/questions/setup/custom-rules";
import { EmptyState, QueryError, TableSkeleton } from "@/components/query-state";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import { ApiError } from "@/lib/api/client";
import {
  useApprovedCurriculum,
  useJudgePrompts,
  useJudgeStats,
  useRevertJudgePrompt,
  useSaveJudgePrompt,
} from "@/lib/api/queries";
import type { JudgePrompt, JudgeStat, JudgeStats, StyleTrust } from "@/lib/api/types";

const SHOWN_METRICS = ["difficulty", "subtopic"] as const;

const JUDGE_LABELS: Record<(typeof SHOWN_METRICS)[number], string> = {
  difficulty: "Difficulty",
  subtopic: "Topic alignment",
};

function isShownJudge(
  prompt: JudgePrompt,
): prompt is JudgePrompt & { metric: (typeof SHOWN_METRICS)[number] } {
  return (SHOWN_METRICS as readonly string[]).includes(prompt.metric);
}

function judgeLabel(prompt: JudgePrompt): string {
  if (prompt.metric === "difficulty" || prompt.metric === "subtopic") {
    return JUDGE_LABELS[prompt.metric];
  }
  return prompt.label;
}

function describeError(error: unknown): string | undefined {
  if (error instanceof ApiError) return error.detail ?? error.message;
  if (error instanceof Error) return error.message;
  return undefined;
}

// Matches the fixed detail string `_gate` writes in judge_learning.py, e.g.
// "Held-out agreement 6/8 (75%) -> 7/8 (88%)." Absent when the gate was
// disabled or too little held-out evidence existed to score a rewrite.
const HELD_OUT_AGREEMENT_RE = /Held-out agreement \d+\/\d+ \((\d+)%\) -> \d+\/\d+ \((\d+)%\)/;

function parseHeldOutAgreement(note: string | null): { before: number; after: number } | null {
  const match = note?.match(HELD_OUT_AGREEMENT_RE);
  if (!match) return null;
  return { before: Number(match[1]), after: Number(match[2]) };
}

function formatUpdatedAt(updatedAt: string | null): string {
  if (!updatedAt) return "never edited";
  return `edited ${new Intl.DateTimeFormat(undefined, {
    month: "short",
    day: "numeric",
    year: "numeric",
  }).format(new Date(updatedAt))}`;
}

function occurrenceKeys(values: readonly string[]): string[] {
  const seen = new Map<string, number>();
  return values.map((value) => {
    const next = (seen.get(value) ?? 0) + 1;
    seen.set(value, next);
    return `${value}::${next}`;
  });
}

function SummaryCard({
  title,
  value,
  hint,
  icon: Icon,
}: {
  title: string;
  value: number;
  hint: string;
  icon: typeof Sparkles;
}) {
  return (
    <Card className="review-panel">
      <CardHeader className="gap-3">
        <div className="flex items-start justify-between gap-3">
          <div>
            <div className="review-eyebrow">{title}</div>
            <CardTitle className="mt-2 text-3xl">{value}</CardTitle>
          </div>
          <div className="rounded-xl border border-border bg-muted p-2 text-muted-foreground">
            <Icon className="size-4" />
          </div>
        </div>
        <CardDescription>{hint}</CardDescription>
      </CardHeader>
    </Card>
  );
}

function JudgeStatusBadges({ prompt }: { prompt: JudgePrompt }) {
  return (
    <div className="flex flex-wrap items-center gap-2">
      <Badge variant={prompt.edited ? "secondary" : "outline"}>
        {prompt.edited ? (prompt.learned ? "learned" : "edited") : "shipped"}
      </Badge>
      {prompt.rules.length > 0 ? (
        <Badge variant="outline">
          {prompt.rules.length} rule{prompt.rules.length === 1 ? "" : "s"}
        </Badge>
      ) : null}
    </div>
  );
}

function percent(rate: number): string {
  return `${Math.round(rate * 100)}%`;
}

function agreementText(stat: JudgeStat | undefined): string {
  if (!stat || stat.observations === 0 || stat.agreement_rate == null) {
    return "No reviewed questions under this prompt yet";
  }
  return `${stat.agreements}/${stat.observations} agreed (${percent(stat.agreement_rate)})`;
}

function rewriteText(stat: JudgeStat | undefined, stats: JudgeStats | undefined): string | null {
  if (!stat || !stats) return null;
  if (!stats.learning_enabled) return "Automatic rewrites are off";
  if (stats.learning_paused) {
    const n = stats.trusted_style_count;
    return `Rewrites paused while ${n} style${n === 1 ? "" : "s"} skip${n === 1 ? "s" : ""} review`;
  }
  const have = Math.min(stat.learnable_disagreements, stat.disagreements_needed);
  return `Next rewrite: ${have} of ${stat.disagreements_needed} disagreements`;
}

// Every window, custom rules included, must be trusted before a style skips review,
// so the shortest one is what the style is still waiting on.
function styleStatus(style: StyleTrust, minimum: number): string {
  const windows = Object.values(style.metrics);
  if (style.trusted) return "Skips review";
  if (windows.some((metric) => metric.audit_revoked)) return "Audit failed";
  const fewest = Math.min(...windows.map((metric) => metric.observations));
  if (fewest < minimum) return `Building trust: ${fewest} of ${minimum} reviews`;
  return "Below 90% agreement";
}

function StyleTrustCard({ stats }: { stats: JudgeStats }) {
  return (
    <Card className="review-panel">
      <CardHeader className="gap-2">
        <div className="review-eyebrow">Trust by style</div>
        <CardTitle className="text-lg">Which styles skip your review</CardTitle>
        <CardDescription>
          A style skips review once, over its last {stats.min_observations} reviewed questions, the
          judges agreed with you and you accepted at least {percent(stats.min_acceptance)} of them.
        </CardDescription>
      </CardHeader>
      <CardContent>
        {stats.styles.length === 0 ? (
          <p className="text-muted-foreground text-sm">No reviewed round questions yet.</p>
        ) : (
          <table className="w-full text-sm">
            <thead className="text-left text-muted-foreground">
              <tr>
                <th className="py-1 font-medium">Style</th>
                <th className="font-medium">Difficulty</th>
                <th className="font-medium">Topic</th>
                <th className="font-medium">Accepted</th>
                <th className="font-medium">Status</th>
              </tr>
            </thead>
            <tbody>
              {stats.styles.map((style) => (
                <tr
                  key={`${style.curriculum_version_id}-${style.style_id}`}
                  className="border-border border-t"
                >
                  <td className="py-2">{style.style_name ?? style.style_id}</td>
                  {(["difficulty", "subtopic", "acceptance"] as const).map((name) => {
                    const metric = style.metrics[name];
                    return (
                      <td key={name} className="tabular-nums">
                        {metric ? `${metric.agreements}/${metric.observations}` : "–"}
                      </td>
                    );
                  })}
                  <td>
                    <Badge variant={style.trusted ? "secondary" : "outline"}>
                      {styleStatus(style, stats.min_observations)}
                    </Badge>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </CardContent>
    </Card>
  );
}

function JudgeCard({
  prompt,
  stat,
  stats,
  onEdit,
  onRevert,
  isReverting,
}: {
  prompt: JudgePrompt & { metric: (typeof SHOWN_METRICS)[number] };
  stat?: JudgeStat;
  stats?: JudgeStats;
  onEdit: (prompt: JudgePrompt) => void;
  onRevert: (prompt: JudgePrompt) => void;
  isReverting: boolean;
}) {
  const ruleKeys = occurrenceKeys(prompt.rules);
  const agreement = parseHeldOutAgreement(prompt.note);
  const label = judgeLabel(prompt);
  const rewrite = rewriteText(stat, stats);

  return (
    <Card className="review-panel h-full">
      <CardHeader className="gap-4">
        <div className="flex flex-wrap items-start justify-between gap-3">
          <div className="space-y-2">
            <div className="review-eyebrow">built-in judge</div>
            <CardTitle className="flex items-center gap-2 text-lg">
              <Gavel className="size-4 text-muted-foreground" />
              {label}
            </CardTitle>
            <JudgeStatusBadges prompt={prompt} />
            {agreement ? (
              <div className="flex items-center gap-1.5 font-semibold text-emerald-700 text-sm dark:text-emerald-300">
                <TrendingUp className="size-4" />
                Held-out agreement {agreement.before}%
                <span className="text-muted-foreground">&rarr;</span>
                {agreement.after}%
              </div>
            ) : null}
          </div>
          <div className="flex flex-wrap items-center gap-2">
            <Button
              variant="outline"
              size="sm"
              onClick={() => onEdit(prompt)}
              disabled={isReverting}
            >
              <Scale className="size-3.5" />
              Edit prompt
            </Button>
            {prompt.edited ? (
              <Button
                variant="ghost"
                size="sm"
                onClick={() => onRevert(prompt)}
                disabled={isReverting}
              >
                <Undo2 className={isReverting ? "size-3.5 animate-spin" : "size-3.5"} />
                {isReverting ? "Reverting" : "Revert"}
              </Button>
            ) : null}
          </div>
        </div>
        <CardDescription className="flex flex-wrap gap-x-4 gap-y-1 text-xs">
          <span>{agreementText(stat)}</span>
          {rewrite ? <span>{rewrite}</span> : null}
          {prompt.revision > 0 ? <span>revision {prompt.revision}</span> : null}
          {prompt.learned ? <span>{prompt.evidence_count} disagreements learned from</span> : null}
          <span>{formatUpdatedAt(prompt.updated_at)}</span>
        </CardDescription>
        {prompt.note ? (
          <p className="text-muted-foreground text-xs italic">“{prompt.note}”</p>
        ) : null}
      </CardHeader>
      <CardContent className="space-y-4">
        <div className="rounded-xl border border-border bg-muted/55 p-4">
          <p className="review-eyebrow mb-2">prompt in force</p>
          <p className="whitespace-pre-wrap text-foreground/90 text-sm leading-6">
            {prompt.system_prompt}
          </p>
        </div>

        {prompt.rules.length > 0 ? (
          <div className="space-y-2">
            <p className="review-eyebrow">learned rules</p>
            <ul className="space-y-2">
              {prompt.rules.map((rule, ruleIndex) => (
                <li
                  key={`${prompt.metric}-${ruleKeys[ruleIndex]}`}
                  className="rounded-xl border border-border bg-background px-3 py-2 text-sm"
                >
                  {rule}
                </li>
              ))}
            </ul>
          </div>
        ) : null}
      </CardContent>
    </Card>
  );
}

function JudgeEditDialog({
  prompt,
  open,
  onOpenChange,
  trustedStyles,
}: {
  prompt: JudgePrompt | null;
  open: boolean;
  onOpenChange: (open: boolean) => void;
  trustedStyles: number;
}) {
  const savePrompt = useSaveJudgePrompt();
  const promptId = useId();
  const noteId = useId();

  // Keyed on the metric below, so opening a different judge remounts with its text.
  const [text, setText] = useState(prompt?.system_prompt ?? "");
  const [note, setNote] = useState("");

  if (!prompt) return null;

  const trimmed = text.trim();
  const changed = trimmed.length > 0 && trimmed !== prompt.system_prompt.trim();
  const matchesShipped = trimmed === prompt.shipped_prompt.trim();

  async function submit(event: React.FormEvent) {
    event.preventDefault();
    if (!prompt || !changed) return;
    try {
      const result = await savePrompt.mutateAsync({
        metric: prompt.metric,
        body: { system_prompt: text, note: note.trim() || null },
      });
      toast.success(`Saved the ${judgeLabel(prompt)} judge`, {
        description: result.rubric_version_changed
          ? `The panel now answers under ${result.rubric_version}.`
          : "The submitted text matched what was already in force.",
      });
      onOpenChange(false);
    } catch (error) {
      toast.error(`Could not save the ${judgeLabel(prompt)} judge`, {
        description: describeError(error),
      });
    }
  }

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="sm:max-w-2xl">
        <form onSubmit={submit} className="space-y-4">
          <DialogHeader>
            <DialogTitle>Edit the {judgeLabel(prompt)} judge</DialogTitle>
            <DialogDescription>
              This replaces the whole system prompt and re-names the panel. Existing evaluations are
              left alone — re-judging the bank under the new prompt is a separate step.
            </DialogDescription>
          </DialogHeader>

          <div className="space-y-2">
            <div className="flex items-center justify-between">
              <Label htmlFor={promptId}>System prompt</Label>
              <Button
                type="button"
                variant="ghost"
                size="sm"
                disabled={matchesShipped}
                onClick={() => setText(prompt.shipped_prompt)}
              >
                Use shipped text
              </Button>
            </div>
            <Textarea
              id={promptId}
              value={text}
              onChange={(event) => setText(event.target.value)}
              className="min-h-64 font-mono text-xs leading-5"
            />
          </div>

          <div className="space-y-2">
            <Label htmlFor={noteId}>
              Note <span className="text-muted-foreground">(optional, why you changed it)</span>
            </Label>
            <Input
              id={noteId}
              value={note}
              maxLength={500}
              onChange={(event) => setNote(event.target.value)}
              placeholder="e.g. stop flagging incidental loop use as off-topic"
            />
          </div>

          {trustedStyles > 0 ? (
            <p className="text-amber-700 text-sm dark:text-amber-300">
              Saving resets trust: {trustedStyles} style{trustedStyles === 1 ? " goes" : "s go"}{" "}
              back to your review until the edited judge earns it again.
            </p>
          ) : null}

          <DialogFooter>
            <Button type="button" variant="ghost" onClick={() => onOpenChange(false)}>
              Cancel
            </Button>
            <Button type="submit" disabled={!changed || savePrompt.isPending}>
              {savePrompt.isPending ? "Saving…" : "Save prompt"}
            </Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  );
}

function TaxonomyCustomRules() {
  const curriculum = useApprovedCurriculum();
  if (curriculum.isPending) return null;
  if (!curriculum.data) {
    return (
      <Card className="review-panel">
        <CardHeader>
          <CardTitle className="text-lg">Custom rules</CardTitle>
          <CardDescription>Approve a taxonomy first.</CardDescription>
        </CardHeader>
      </Card>
    );
  }
  return <CustomRules curriculumVersionId={curriculum.data.version.id} />;
}

export function JudgesScreen() {
  const { data, error, isPending } = useJudgePrompts();
  const revertPrompt = useRevertJudgePrompt();
  const stats = useJudgeStats().data;

  const [editing, setEditing] = useState<JudgePrompt | null>(null);
  const [editOpen, setEditOpen] = useState(false);

  const shown = (data?.prompts ?? []).filter(isShownJudge);
  const prompts = SHOWN_METRICS.flatMap((metric) => {
    const prompt = shown.find((item) => item.metric === metric);
    return prompt ? [prompt] : [];
  });
  const editedCount = prompts.filter((prompt) => prompt.edited).length;
  const learnedCount = prompts.filter((prompt) => prompt.learned).length;
  const diverged = data != null && data.rubric_version !== data.shipped_rubric_version;

  function openEditor(prompt: JudgePrompt) {
    setEditing(prompt);
    setEditOpen(true);
  }

  async function handleRevert(prompt: JudgePrompt) {
    try {
      const result = await revertPrompt.mutateAsync(prompt.metric);
      toast.success(`Reverted the ${judgeLabel(prompt)} judge`, {
        description: `Running the shipped prompt again — panel ${result.rubric_version}.`,
      });
    } catch (error) {
      toast.error(`Could not revert the ${judgeLabel(prompt)} judge`, {
        description: describeError(error),
      });
    }
  }

  return (
    <div className="space-y-6">
      {error ? <QueryError error={error} /> : null}

      {isPending ? (
        <TableSkeleton rows={2} />
      ) : prompts.length === 0 ? (
        <EmptyState
          title="No judge prompts yet"
          hint="The API returned no difficulty or topic-alignment judge, so there is nothing to display."
        />
      ) : (
        <>
          <div className="grid gap-4 md:grid-cols-2">
            <SummaryCard
              title="Edited"
              value={editedCount}
              hint="Judges running a prompt other than the one they shipped with."
              icon={Scale}
            />
            <SummaryCard
              title="Learned"
              value={learnedCount}
              hint="Judges whose current prompt was rewritten from disagreements, not typed."
              icon={Sparkles}
            />
          </div>

          <Card className="review-panel">
            <CardHeader className="gap-2">
              <div className="review-eyebrow">Rubric version</div>
              <CardTitle className="text-lg">
                {data?.rubric_version}
                {diverged ? (
                  <Badge variant="outline" className="ml-2 align-middle">
                    shipped: {data?.shipped_rubric_version}
                  </Badge>
                ) : null}
              </CardTitle>
              <CardDescription>
                Every evaluation written from now on carries this name. Editing a judge below
                changes it, which is what lets calibration report a repaired judge separately from
                the one it replaced.
              </CardDescription>
            </CardHeader>
          </Card>

          <div className="grid gap-4 xl:grid-cols-2">
            {prompts.map((prompt) => (
              <JudgeCard
                key={prompt.metric}
                prompt={prompt}
                stat={stats?.judges.find((item) => item.metric === prompt.metric)}
                stats={stats}
                onEdit={openEditor}
                onRevert={handleRevert}
                isReverting={revertPrompt.isPending && revertPrompt.variables === prompt.metric}
              />
            ))}
          </div>

          {stats ? <StyleTrustCard stats={stats} /> : null}
        </>
      )}

      <TaxonomyCustomRules />

      <JudgeEditDialog
        key={editing?.metric ?? "none"}
        prompt={editing}
        open={editOpen}
        onOpenChange={setEditOpen}
        trustedStyles={stats?.trusted_style_count ?? 0}
      />
    </div>
  );
}
