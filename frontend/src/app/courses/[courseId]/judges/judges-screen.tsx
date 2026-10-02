"use client";

/**
 * The four advisory judges, one card each, backed by `GET /api/judge-prompts`.
 *
 * A judge is repaired by rewriting its system prompt (ADR-038) or by re-learning
 * it from the questions it got wrong (ADR-039). Saving either way re-names the
 * panel, so the rubric version the panel currently answers under is shown
 * against the version it shipped with.
 */

import { Gavel, RefreshCw, Scale, Sparkles, TrendingUp, Undo2 } from "lucide-react";
import { useId, useState } from "react";
import { toast } from "sonner";
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
  useJudgePrompts,
  useRefreshJudgePrompt,
  useRevertJudgePrompt,
  useSaveJudgePrompt,
} from "@/lib/api/queries";
import type { JudgePrompt } from "@/lib/api/types";

function describeError(error: unknown): string | undefined {
  if (error instanceof ApiError) return error.detail ?? error.message;
  if (error instanceof Error) return error.message;
  return undefined;
}

function capitalize(text: string): string {
  return text.charAt(0).toUpperCase() + text.slice(1);
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
  const unlearned = Math.max(0, prompt.available_disagreements - prompt.evidence_count);
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
      {prompt.available_disagreements > 0 ? (
        <Badge variant={unlearned > 0 ? "outline" : "secondary"}>
          {unlearned > 0
            ? `${unlearned} new disagreement${unlearned === 1 ? "" : "s"}`
            : "up to date"}
        </Badge>
      ) : null}
    </div>
  );
}

function JudgeCard({
  prompt,
  onEdit,
  onRevert,
  onRefresh,
  isReverting,
  isRefreshing,
}: {
  prompt: JudgePrompt;
  onEdit: (prompt: JudgePrompt) => void;
  onRevert: (prompt: JudgePrompt) => void;
  onRefresh: (prompt: JudgePrompt) => void;
  isReverting: boolean;
  isRefreshing: boolean;
}) {
  const busy = isReverting || isRefreshing;
  const ruleKeys = occurrenceKeys(prompt.rules);
  const agreement = parseHeldOutAgreement(prompt.note);

  return (
    <Card className="review-panel h-full">
      <CardHeader className="gap-4">
        <div className="flex flex-wrap items-start justify-between gap-3">
          <div className="space-y-2">
            <div className="review-eyebrow">advisory judge</div>
            <CardTitle className="flex items-center gap-2 text-lg">
              <Gavel className="size-4 text-muted-foreground" />
              {capitalize(prompt.label)}
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
            <Button variant="outline" size="sm" onClick={() => onEdit(prompt)} disabled={busy}>
              <Scale className="size-3.5" />
              Edit prompt
            </Button>
            {prompt.edited ? (
              <Button variant="ghost" size="sm" onClick={() => onRevert(prompt)} disabled={busy}>
                <Undo2 className={isReverting ? "size-3.5 animate-spin" : "size-3.5"} />
                {isReverting ? "Reverting" : "Revert"}
              </Button>
            ) : null}
            {prompt.available_disagreements > 0 ? (
              <Button variant="outline" size="sm" onClick={() => onRefresh(prompt)} disabled={busy}>
                <RefreshCw className={isRefreshing ? "size-3.5 animate-spin" : "size-3.5"} />
                {isRefreshing ? "Re-learning" : "Re-learn"}
              </Button>
            ) : null}
          </div>
        </div>
        <CardDescription className="flex flex-wrap gap-x-4 gap-y-1 text-xs">
          {prompt.revision > 0 ? <span>revision {prompt.revision}</span> : null}
          {prompt.learned ? <span>{prompt.evidence_count} disagreements learned from</span> : null}
          <span>{prompt.available_disagreements} available to learn from</span>
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
}: {
  prompt: JudgePrompt | null;
  open: boolean;
  onOpenChange: (open: boolean) => void;
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
      toast.success(`Saved the ${prompt.label} judge`, {
        description: result.rubric_version_changed
          ? `The panel now answers under ${result.rubric_version}.`
          : "The submitted text matched what was already in force.",
      });
      onOpenChange(false);
    } catch (error) {
      toast.error(`Could not save the ${prompt.label} judge`, {
        description: describeError(error),
      });
    }
  }

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="sm:max-w-2xl">
        <form onSubmit={submit} className="space-y-4">
          <DialogHeader>
            <DialogTitle>Edit the {prompt.label} judge</DialogTitle>
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

export function JudgesScreen() {
  const { data, error, isPending } = useJudgePrompts();
  const revertPrompt = useRevertJudgePrompt();
  const refreshPrompt = useRefreshJudgePrompt();

  const [editing, setEditing] = useState<JudgePrompt | null>(null);
  const [editOpen, setEditOpen] = useState(false);

  const prompts = data?.prompts ?? [];
  const editedCount = prompts.filter((prompt) => prompt.edited).length;
  const learnedCount = prompts.filter((prompt) => prompt.learned).length;
  const refreshReadyCount = prompts.filter((prompt) => prompt.available_disagreements > 0).length;
  const diverged = data != null && data.rubric_version !== data.shipped_rubric_version;

  function openEditor(prompt: JudgePrompt) {
    setEditing(prompt);
    setEditOpen(true);
  }

  async function handleRevert(prompt: JudgePrompt) {
    try {
      const result = await revertPrompt.mutateAsync(prompt.metric);
      toast.success(`Reverted the ${prompt.label} judge`, {
        description: `Running the shipped prompt again — panel ${result.rubric_version}.`,
      });
    } catch (error) {
      toast.error(`Could not revert the ${prompt.label} judge`, {
        description: describeError(error),
      });
    }
  }

  async function handleRefresh(prompt: JudgePrompt) {
    try {
      const result = await refreshPrompt.mutateAsync(prompt.metric);
      if (!result.learned) {
        toast.info(`Nothing new to learn for the ${prompt.label} judge`, {
          description: "No attributable disagreement was available, so the prompt is unchanged.",
        });
        return;
      }
      toast.success(`Re-learned the ${prompt.label} judge`, {
        description: `${result.rule_count} rule${
          result.rule_count === 1 ? "" : "s"
        } from ${result.evidence_count} disagreement${result.evidence_count === 1 ? "" : "s"}.`,
      });
    } catch (error) {
      toast.error(`Could not re-learn the ${prompt.label} judge`, {
        description: describeError(error),
      });
    }
  }

  return (
    <div className="space-y-6">
      {error ? <QueryError error={error} /> : null}

      {isPending ? (
        <TableSkeleton rows={4} />
      ) : prompts.length === 0 ? (
        <EmptyState
          title="No judge prompts yet"
          hint="The API returned no judges, so there is nothing to display."
        />
      ) : (
        <>
          <div className="grid gap-4 md:grid-cols-3">
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
            <SummaryCard
              title="Refresh ready"
              value={refreshReadyCount}
              hint="Judges with at least one attributable disagreement available to learn from."
              icon={RefreshCw}
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
                Every evaluation written from now on carries this name. Editing or re-learning any
                judge below changes it, which is what lets calibration report a repaired judge
                separately from the one it replaced.
              </CardDescription>
            </CardHeader>
          </Card>

          <div className="grid gap-4 xl:grid-cols-2">
            {prompts.map((prompt) => (
              <JudgeCard
                key={prompt.metric}
                prompt={prompt}
                onEdit={openEditor}
                onRevert={handleRevert}
                onRefresh={handleRefresh}
                isReverting={revertPrompt.isPending && revertPrompt.variables === prompt.metric}
                isRefreshing={refreshPrompt.isPending && refreshPrompt.variables === prompt.metric}
              />
            ))}
          </div>
        </>
      )}

      <JudgeEditDialog
        key={editing?.metric ?? "none"}
        prompt={editing}
        open={editOpen}
        onOpenChange={setEditOpen}
      />
    </div>
  );
}
