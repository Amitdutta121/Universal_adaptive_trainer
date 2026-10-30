"use client";

/**
 * The "New course" modal on My courses: a name, an optional description and a subject.
 *
 * The subject decides the question style library, the tutorial recipes, the prompts' wording
 * and the question types the course starts with (ADR-054). Question types are not asked here:
 * question setup chooses styles per subtopic later, with examples, and the course-wide list is
 * in course Settings. A subject without a style library is shown as "Coming soon", because its
 * course could not get past question setup. Everything comes from `GET /api/courses/catalog`.
 */

import { useMemo, useState } from "react";
import { QueryError } from "@/components/query-state";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Skeleton } from "@/components/ui/skeleton";
import { Textarea } from "@/components/ui/textarea";
import { useAssessmentCatalog, useCreateCourse } from "@/lib/api/queries";
import { coursePath } from "@/lib/course";
import { cn } from "@/lib/utils";

export function NewCourseDialog({ onOpenChange }: { onOpenChange: (open: boolean) => void }) {
  const catalog = useAssessmentCatalog();
  const createCourse = useCreateCourse();
  const [name, setName] = useState("");
  const [description, setDescription] = useState("");
  const [subjectId, setSubjectId] = useState<string | null>(null);

  const subject = catalog.data?.subjects.find((entry) => entry.id === subjectId) ?? null;
  const labels = useMemo(
    () => new Map((catalog.data?.question_types ?? []).map((type) => [type.id, type.label])),
    [catalog.data],
  );

  async function create() {
    if (!subject?.ready || !name.trim()) return;
    try {
      const course = await createCourse.mutateAsync({
        name: name.trim(),
        description: description.trim() || null,
        // No question_types: the server stores the subject's defaults.
        subject: subject.id,
      });
      // A full load into the new course: query keys do not name a course (see courses-screen).
      window.location.assign(coursePath(course.id, "/dashboard"));
    } catch {
      // Rendered below with the backend's own wording.
    }
  }

  return (
    <Dialog open onOpenChange={(next) => !createCourse.isPending && onOpenChange(next)}>
      <DialogContent className="flex max-h-[90vh] flex-col gap-0 overflow-hidden p-0 sm:max-w-3xl">
        <DialogHeader className="border-b px-6 pt-5 pb-4">
          <DialogTitle className="text-lg">New course</DialogTitle>
          <DialogDescription>
            Name the course and pick its subject. You choose question styles per topic later, in
            question setup.
          </DialogDescription>
        </DialogHeader>

        <div className="min-h-0 flex-1 overflow-y-auto px-6 py-5">
          {catalog.isError ? <QueryError error={catalog.error} /> : null}
          {catalog.isPending ? <Skeleton className="h-72" /> : null}

          {catalog.data ? (
            <div className="space-y-5">
              <div className="grid gap-4 md:grid-cols-2">
                <div className="space-y-2">
                  <Label htmlFor="new-course-name">Course name</Label>
                  <Input
                    id="new-course-name"
                    value={name}
                    maxLength={200}
                    placeholder="e.g. CS 135 · Intro to Programming"
                    onChange={(event) => setName(event.target.value)}
                  />
                </div>
                <div className="space-y-2">
                  <Label htmlFor="new-course-description">
                    Description <span className="text-muted-foreground">(optional)</span>
                  </Label>
                  <Textarea
                    id="new-course-description"
                    value={description}
                    maxLength={2000}
                    className="h-[2.4rem] min-h-0"
                    placeholder="Term, section, who it is for…"
                    onChange={(event) => setDescription(event.target.value)}
                  />
                </div>
              </div>
              <fieldset className="space-y-2">
                <legend className="mb-2 font-medium text-sm">Subject</legend>
                <div className="grid gap-3 md:grid-cols-2">
                  {catalog.data.subjects.map((entry) => {
                    const selected = entry.id === subjectId;
                    const given = entry.default_types.map((id) => labels.get(id) ?? id);
                    return (
                      <button
                        key={entry.id}
                        type="button"
                        aria-pressed={selected}
                        disabled={!entry.ready}
                        onClick={() => setSubjectId(entry.id)}
                        className={cn(
                          "rounded-xl border p-4 text-left transition-colors",
                          entry.ready ? "hover:bg-muted/40" : "cursor-not-allowed opacity-60",
                          selected && "border-primary ring-1 ring-primary",
                        )}
                      >
                        <div className="flex flex-wrap items-center gap-2">
                          <span className="font-medium text-sm">{entry.label}</span>
                          {entry.ready ? null : (
                            <Badge variant="outline" className="font-normal text-[11px]">
                              Coming soon
                            </Badge>
                          )}
                        </div>
                        <div className="mt-1 text-muted-foreground text-xs">
                          {entry.ready
                            ? given.join(" · ")
                            : "No question styles for this subject yet, so its courses cannot set up questions."}
                        </div>
                      </button>
                    );
                  })}
                </div>
              </fieldset>
              <p className="text-muted-foreground text-xs">
                The subject decides the question styles, tutorial styles and wording the AI uses.
                The question types it allows can be changed later in course Settings.
              </p>
            </div>
          ) : null}
        </div>

        {createCourse.error ? (
          <div className="border-t px-6 py-3">
            <QueryError error={createCourse.error} />
          </div>
        ) : null}
        <div className="flex flex-wrap items-center gap-3 border-t px-6 py-4">
          <Button variant="ghost" size="sm" onClick={() => onOpenChange(false)}>
            Cancel
          </Button>
          <span className="text-muted-foreground text-sm">
            {!name.trim()
              ? "Name the course and pick a subject."
              : subject
                ? `${subject.label}`
                : "Pick a subject to continue."}
          </span>
          <Button
            size="sm"
            className="ml-auto"
            disabled={!subject?.ready || !name.trim() || createCourse.isPending}
            onClick={() => void create()}
          >
            {createCourse.isPending ? "Creating…" : "Create course"}
          </Button>
        </div>
      </DialogContent>
    </Dialog>
  );
}
