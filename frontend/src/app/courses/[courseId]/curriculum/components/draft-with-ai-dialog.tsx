"use client";

/**
 * Describe the taxonomy you want and have the AI propose it (ADR-052).
 *
 * The proposal is not saved: it is handed to the page, which opens it in the builder,
 * and it becomes a curriculum version only when the professor saves it there. Nothing
 * here is written back to the course either -- these words describe this taxonomy.
 *
 * The same form also sits beside the builder once a draft is open (`variant="panel"`), so
 * the professor can change the request and draft again until the result is right.
 */

import { Sparkles } from "lucide-react";
import { useEffect, useId, useRef, useState } from "react";
import { QueryError } from "@/components/query-state";
import { Button } from "@/components/ui/button";
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
import { useCourse, useDraftTaxonomy } from "@/lib/api/queries";
import { useCourseId } from "@/lib/use-course";
import type { VersionTopic } from "../builder/taxonomy-draft";

/** Quick picks that fill in the subtopic count (`SIZE_TARGETS` in `app/curriculum/drafting.py`). */
const PRESETS: Array<{ label: string; subtopics: number }> = [
  { label: "Fewer, broader", subtopics: 15 },
  { label: "Balanced", subtopics: 30 },
  { label: "Fine-grained", subtopics: 45 },
];

/** A count field's value: a whole number in range, or `null` for "let the AI decide". */
function count(value: string, max: number): number | null {
  const parsed = Number(value);
  return value.trim() === "" || !Number.isInteger(parsed) || parsed < 1 || parsed > max
    ? null
    : parsed;
}

export interface TaxonomyDraft {
  draftedBy: string;
  analysis: string;
  document: { label: string; topics: VersionTopic[] };
}

function Optional() {
  return <span className="text-muted-foreground">(optional)</span>;
}

/** What the professor typed, kept so the panel beside the builder starts from the same request. */
export interface DraftRequest {
  title: string;
  description: string;
  audience: string;
  mustCover: string;
  leaveOut: string;
  subtopics: string;
  topics: string;
}

export function DraftWithAiDialog({
  open,
  onOpenChange,
  onDrafted,
}: {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  onDrafted: (draft: TaxonomyDraft, request: DraftRequest) => void;
}) {
  const [pending, setPending] = useState(false);
  return (
    <Dialog open={open} onOpenChange={(next) => !pending && onOpenChange(next)}>
      <DialogContent className="max-h-[92vh] overflow-y-auto sm:max-w-xl">
        <DraftWithAiForm
          variant="dialog"
          onPendingChange={setPending}
          onCancel={() => onOpenChange(false)}
          onDrafted={onDrafted}
        />
      </DialogContent>
    </Dialog>
  );
}

export function DraftWithAiForm({
  variant,
  initial,
  onDrafted,
  onCancel,
  onPendingChange,
}: {
  variant: "dialog" | "panel";
  /** The request to start from; without one the course's name and description are used. */
  initial?: DraftRequest;
  onDrafted: (draft: TaxonomyDraft, request: DraftRequest) => void;
  onCancel?: () => void;
  onPendingChange?: (pending: boolean) => void;
}) {
  const course = useCourse(useCourseId());
  const draft = useDraftTaxonomy();
  const ids = {
    title: useId(),
    description: useId(),
    audience: useId(),
    mustCover: useId(),
    leaveOut: useId(),
    subtopics: useId(),
    topics: useId(),
  };
  const [title, setTitle] = useState(initial?.title ?? "");
  const [description, setDescription] = useState(initial?.description ?? "");
  const [audience, setAudience] = useState(initial?.audience ?? "");
  const [mustCover, setMustCover] = useState(initial?.mustCover ?? "");
  const [leaveOut, setLeaveOut] = useState(initial?.leaveOut ?? "");
  // The professor's own numbers; empty lets the AI decide (about 30 subtopics).
  const [subtopics, setSubtopics] = useState(initial?.subtopics ?? "30");
  const [topics, setTopics] = useState(initial?.topics ?? "");

  // Start from the course's own name and description; both are only a starting point.
  const [prefilled, setPrefilled] = useState(initial !== undefined);
  useEffect(() => {
    if (prefilled || !course.data) return;
    setTitle(course.data.name);
    setDescription(course.data.description ?? "");
    setPrefilled(true);
  }, [course.data, prefilled]);

  const onPendingChangeRef = useRef(onPendingChange);
  onPendingChangeRef.current = onPendingChange;
  useEffect(() => {
    onPendingChangeRef.current?.(draft.isPending);
  }, [draft.isPending]);

  const subtopicCount = count(subtopics, 80);
  const topicCount = count(topics, 20);
  const countError =
    (subtopics.trim() !== "" && subtopicCount === null) ||
    (topics.trim() !== "" && topicCount === null)
      ? "Use a whole number: up to 80 subtopics and 20 topics."
      : subtopicCount !== null && topicCount !== null && subtopicCount < topicCount
        ? "Every topic needs at least one subtopic."
        : null;
  const ready = title.trim() !== "" && description.trim() !== "" && countError === null;

  async function submit(event: React.FormEvent) {
    event.preventDefault();
    if (!ready) return;
    try {
      const result = await draft.mutateAsync({
        title: title.trim(),
        description: description.trim(),
        audience: audience.trim(),
        must_cover: mustCover.trim(),
        leave_out: leaveOut.trim(),
        // The fallback when both counts are empty: about 30 subtopics.
        size: "standard",
        subtopic_count: subtopicCount,
        topic_count: topicCount,
      });
      onDrafted(
        {
          draftedBy: result.drafted_by,
          analysis: result.analysis,
          document: result.document as TaxonomyDraft["document"],
        },
        { title, description, audience, mustCover, leaveOut, subtopics, topics },
      );
    } catch {
      // Rendered below with the backend's own wording.
    }
  }

  const panel = variant === "panel";

  return (
    <form onSubmit={submit} className="space-y-4">
      {panel ? (
        <div className="space-y-1">
          <h2 className="font-medium text-sm">AI request</h2>
          <p className="text-muted-foreground text-xs">
            {initial
              ? "Change anything and draft again; the new draft replaces the one in the builder."
              : "Describe the course; the draft appears in the builder for you to review."}
          </p>
        </div>
      ) : (
        <DialogHeader>
          <DialogTitle>Draft a curriculum with AI</DialogTitle>
          <DialogDescription>
            Describe the course. The AI proposes topics and subtopics, and the draft opens in the
            builder for you to review; nothing is saved until you save it there.
          </DialogDescription>
        </DialogHeader>
      )}

      <fieldset disabled={draft.isPending} className="space-y-4">
        <div className="space-y-2">
          <Label htmlFor={ids.title}>Title</Label>
          <Input
            id={ids.title}
            value={title}
            maxLength={200}
            placeholder="Intro Biology"
            onChange={(event) => setTitle(event.target.value)}
          />
        </div>

        <div className="space-y-2">
          <Label htmlFor={ids.description}>Description</Label>
          <Textarea
            id={ids.description}
            value={description}
            maxLength={4000}
            className="h-[5.5rem]"
            placeholder="What the course covers and what students should be able to do by the end."
            onChange={(event) => setDescription(event.target.value)}
          />
        </div>

        <div className="space-y-2">
          <Label htmlFor={ids.audience}>
            Audience and level <Optional />
          </Label>
          <Input
            id={ids.audience}
            value={audience}
            maxLength={1000}
            placeholder="First-year undergraduates, no prior experience"
            onChange={(event) => setAudience(event.target.value)}
          />
        </div>

        <div className="space-y-2">
          <Label htmlFor={ids.mustCover}>
            Must cover <Optional />
          </Label>
          <Textarea
            id={ids.mustCover}
            value={mustCover}
            maxLength={8000}
            className="h-[6rem]"
            placeholder={
              "Topics or learning outcomes, one per line. A pasted syllabus works.\nMitosis and meiosis\nNatural selection"
            }
            onChange={(event) => setMustCover(event.target.value)}
          />
          <p className="text-muted-foreground text-xs">
            Everything listed here will appear in the draft.
          </p>
        </div>

        <div className="space-y-2">
          <Label htmlFor={ids.leaveOut}>
            Leave out <Optional />
          </Label>
          <Input
            id={ids.leaveOut}
            value={leaveOut}
            maxLength={2000}
            placeholder="Lab techniques, history of the field"
            onChange={(event) => setLeaveOut(event.target.value)}
          />
        </div>

        <fieldset className="space-y-2">
          <legend className="font-medium text-sm">How many topics and subtopics</legend>
          <div className="flex flex-wrap gap-2">
            {PRESETS.map((preset) => (
              <Button
                key={preset.label}
                type="button"
                size="sm"
                variant={
                  subtopicCount === preset.subtopics && topicCount === null
                    ? "secondary"
                    : "outline"
                }
                onClick={() => {
                  setSubtopics(String(preset.subtopics));
                  setTopics("");
                }}
              >
                {preset.label} · {preset.subtopics}
              </Button>
            ))}
          </div>
          <div className="grid grid-cols-2 gap-3">
            <div className="space-y-1">
              <Label htmlFor={ids.subtopics} className="font-normal text-xs">
                Subtopics in total
              </Label>
              <Input
                id={ids.subtopics}
                type="number"
                inputMode="numeric"
                min={1}
                max={80}
                value={subtopics}
                placeholder="AI decides"
                onChange={(event) => setSubtopics(event.target.value)}
              />
            </div>
            <div className="space-y-1">
              <Label htmlFor={ids.topics} className="font-normal text-xs">
                Topics <Optional />
              </Label>
              <Input
                id={ids.topics}
                type="number"
                inputMode="numeric"
                min={1}
                max={20}
                value={topics}
                placeholder="AI groups them"
                onChange={(event) => setTopics(event.target.value)}
              />
            </div>
          </div>
          {countError ? (
            <p className="text-destructive text-xs">{countError}</p>
          ) : (
            <p className="text-muted-foreground text-xs">
              The AI is asked to match these exactly; you can still add or remove rows in the
              builder. Leave a field empty to let the AI decide.
            </p>
          )}
        </fieldset>
      </fieldset>

      {draft.isPending ? (
        <p className="text-muted-foreground text-sm">
          Drafting… this usually takes under a minute.
        </p>
      ) : null}
      {draft.error ? <QueryError error={draft.error} /> : null}

      {panel ? (
        <Button type="submit" className="w-full" disabled={!ready || draft.isPending}>
          <Sparkles />
          {draft.isPending ? "Drafting…" : initial ? "Draft again" : "Draft curriculum"}
        </Button>
      ) : (
        <DialogFooter>
          <Button type="button" variant="ghost" disabled={draft.isPending} onClick={onCancel}>
            Cancel
          </Button>
          <Button type="submit" disabled={!ready || draft.isPending}>
            <Sparkles />
            {draft.isPending ? "Drafting…" : "Draft curriculum"}
          </Button>
        </DialogFooter>
      )}
    </form>
  );
}
