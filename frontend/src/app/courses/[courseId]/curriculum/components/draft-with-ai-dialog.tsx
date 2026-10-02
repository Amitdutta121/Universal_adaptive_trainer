"use client";

/**
 * Describe the taxonomy you want and have the AI propose it (ADR-052).
 *
 * The proposal is not saved: it is handed to the page, which opens it in the builder,
 * and it becomes a curriculum version only when the professor saves it there. Nothing
 * here is written back to the course either -- these words describe this taxonomy.
 */

import { Sparkles } from "lucide-react";
import { useEffect, useId, useState } from "react";
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
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { Textarea } from "@/components/ui/textarea";
import { useCourse, useDraftTaxonomy } from "@/lib/api/queries";
import type { Schemas } from "@/lib/api/types";
import { useCourseId } from "@/lib/use-course";
import type { VersionTopic } from "../builder/taxonomy-draft";

type DraftSize = Schemas["TaxonomyDraftRequest"]["size"] & string;

/** Mirrors `SIZE_TARGETS` in `app/curriculum/drafting.py`; each subtopic needs ~9 reviewed questions. */
const SIZES: Array<{ value: DraftSize; label: string; hint: string }> = [
  { value: "compact", label: "Compact", hint: "about 15 subtopics, ~135 questions to review" },
  { value: "standard", label: "Standard", hint: "about 30 subtopics, ~270 questions to review" },
  { value: "detailed", label: "Detailed", hint: "about 45 subtopics, ~405 questions to review" },
];

export interface TaxonomyDraft {
  draftedBy: string;
  analysis: string;
  document: { label: string; topics: VersionTopic[] };
}

function Optional() {
  return <span className="text-muted-foreground">(optional)</span>;
}

export function DraftWithAiDialog({
  open,
  onOpenChange,
  onDrafted,
}: {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  onDrafted: (draft: TaxonomyDraft) => void;
}) {
  const course = useCourse(useCourseId());
  const draft = useDraftTaxonomy();
  const ids = {
    title: useId(),
    description: useId(),
    audience: useId(),
    mustCover: useId(),
    leaveOut: useId(),
    size: useId(),
  };
  const [title, setTitle] = useState("");
  const [description, setDescription] = useState("");
  const [audience, setAudience] = useState("");
  const [mustCover, setMustCover] = useState("");
  const [leaveOut, setLeaveOut] = useState("");
  const [size, setSize] = useState<DraftSize>("standard");

  // Start from the course's own name and description; both are only a starting point.
  const [prefilled, setPrefilled] = useState(false);
  useEffect(() => {
    if (prefilled || !course.data) return;
    setTitle(course.data.name);
    setDescription(course.data.description ?? "");
    setPrefilled(true);
  }, [course.data, prefilled]);

  const ready = title.trim() !== "" && description.trim() !== "";

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
        size,
      });
      onDrafted({
        draftedBy: result.drafted_by,
        analysis: result.analysis,
        document: result.document as TaxonomyDraft["document"],
      });
    } catch {
      // Rendered below with the backend's own wording.
    }
  }

  return (
    <Dialog open={open} onOpenChange={(next) => !draft.isPending && onOpenChange(next)}>
      <DialogContent className="max-h-[92vh] overflow-y-auto sm:max-w-xl">
        <form onSubmit={submit} className="space-y-4">
          <DialogHeader>
            <DialogTitle>Draft a taxonomy with AI</DialogTitle>
            <DialogDescription>
              Describe the course. The AI proposes topics and subtopics, and the draft opens in the
              builder for you to review; nothing is saved until you save it there.
            </DialogDescription>
          </DialogHeader>

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

            <div className="space-y-2">
              <Label htmlFor={ids.size}>Size</Label>
              <Select value={size} onValueChange={(value) => setSize(value as DraftSize)}>
                <SelectTrigger id={ids.size} className="w-full">
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  {SIZES.map((option) => (
                    <SelectItem key={option.value} value={option.value}>
                      {option.label} — {option.hint}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>
          </fieldset>

          {draft.isPending ? (
            <p className="text-muted-foreground text-sm">
              Drafting… this usually takes under a minute.
            </p>
          ) : null}
          {draft.error ? <QueryError error={draft.error} /> : null}

          <DialogFooter>
            <Button
              type="button"
              variant="ghost"
              disabled={draft.isPending}
              onClick={() => onOpenChange(false)}
            >
              Cancel
            </Button>
            <Button type="submit" disabled={!ready || draft.isPending}>
              <Sparkles />
              {draft.isPending ? "Drafting…" : "Draft taxonomy"}
            </Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  );
}
