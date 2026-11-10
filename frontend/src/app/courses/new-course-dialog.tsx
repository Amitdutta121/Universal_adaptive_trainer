"use client";

/**
 * The "New course" modal on My courses: a name and an optional description, nothing else.
 *
 * The course is then set up by chatting, on the course assistant page it opens on
 * (`app/courses/[courseId]/assistant`). The assistant sets the
 * subject (`set_course_subject`) once it knows what is taught; until then the course is
 * "Something else" (`custom`), so nothing about any one subject is assumed.
 */

import { useState } from "react";
import { QueryError } from "@/components/query-state";
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
import { Textarea } from "@/components/ui/textarea";
import { useCreateCourse } from "@/lib/api/queries";
import { coursePath } from "@/lib/course";

export function NewCourseDialog({ onOpenChange }: { onOpenChange: (open: boolean) => void }) {
  const createCourse = useCreateCourse();
  const [name, setName] = useState("");
  const [description, setDescription] = useState("");

  async function create() {
    if (!name.trim()) return;
    try {
      const course = await createCourse.mutateAsync({
        name: name.trim(),
        description: description.trim() || null,
        // No subject is assumed: "Something else" until the assistant sets the real one from
        // what the professor teaches (`set_course_subject`).
        subject: "custom",
      });
      // A full load into the new course: query keys do not name a course (see courses-screen).
      window.location.assign(coursePath(course.id, "/assistant"));
    } catch {
      // Rendered below with the backend's own wording.
    }
  }

  return (
    <Dialog open onOpenChange={(next) => !createCourse.isPending && onOpenChange(next)}>
      <DialogContent className="sm:max-w-lg">
        <DialogHeader>
          <DialogTitle className="text-lg">New course</DialogTitle>
          <DialogDescription>The course assistant sets up the rest with you.</DialogDescription>
        </DialogHeader>
        <form
          className="space-y-4"
          onSubmit={(event) => {
            event.preventDefault();
            void create();
          }}
        >
          <div className="space-y-2">
            <Label htmlFor="new-course-name">Course name</Label>
            <Input
              id="new-course-name"
              value={name}
              maxLength={200}
              autoFocus
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
              rows={2}
              placeholder="Term, section, who it is for…"
              onChange={(event) => setDescription(event.target.value)}
            />
          </div>
          {createCourse.error ? <QueryError error={createCourse.error} /> : null}
          <div className="flex justify-end gap-2">
            <Button type="button" variant="ghost" size="sm" onClick={() => onOpenChange(false)}>
              Cancel
            </Button>
            <Button type="submit" size="sm" disabled={!name.trim() || createCourse.isPending}>
              {createCourse.isPending ? "Creating…" : "Create course"}
            </Button>
          </div>
        </form>
      </DialogContent>
    </Dialog>
  );
}
