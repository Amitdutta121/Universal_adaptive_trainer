"use client";

/**
 * "My courses": where a professor lands after signing in.
 *
 * Every figure comes from `GET /api/courses/overview`, which derives it from rows
 * that already exist. Things the product does not track yet -- terms and weekly
 * schedules, co-instructors, background jobs, AI spend, student reports -- are
 * deliberately absent rather than shown as placeholders.
 *
 * Opening a course is a full page load rather than a client-side push. Query
 * keys do not name a course, so a client-side switch would briefly show the
 * previous course's cached books; a fresh document starts from an empty cache.
 */

import { LogOut, Plus } from "lucide-react";
import type { Route } from "next";
import { useRouter } from "next/navigation";
import { useId, useState } from "react";
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
import { Skeleton } from "@/components/ui/skeleton";
import { Textarea } from "@/components/ui/textarea";
import { VerifyEmailBanner } from "@/components/verify-email-banner";
import { useCoursesOverview, useCurrentUser, useLogout, useUpdateCourse } from "@/lib/api/queries";
import type { Schemas } from "@/lib/api/types";
import { coursePath } from "@/lib/course";
import { NewCourseDialog } from "./new-course-dialog";

type CourseProgress = Schemas["CourseProgressOut"];
type ActivityEvent = Schemas["ActivityEventOut"];

/** Each setup step: its label, and the screen that completes it. */
const STEPS: Record<string, { label: string; action: string; path: string }> = {
  materials: { label: "Materials", action: "Add a book", path: "/books" },
  taxonomy: { label: "Taxonomy", action: "Define the taxonomy", path: "/curriculum" },
  coverage: { label: "Coverage", action: "Fill coverage gaps", path: "/coverage" },
  review: { label: "Review", action: "Review questions", path: "/review" },
  question_set: { label: "Question set", action: "Freeze a question set", path: "/coverage" },
  classes: { label: "Classes", action: "Open a classroom", path: "/students" },
};

function openCourse(courseId: number, path = "/books") {
  window.location.assign(coursePath(courseId, path));
}

function plural(count: number, one: string, many = `${one}s`) {
  return `${count.toLocaleString()} ${count === 1 ? one : many}`;
}

function percent(value: number | null | undefined) {
  return value === null || value === undefined ? "—" : `${Math.round(value * 100)}%`;
}

function timeAgo(iso: string) {
  // The API's timestamps are UTC; a naive one is read as UTC, not local time.
  const at = new Date(/[zZ]|[+-]\d\d:\d\d$/.test(iso) ? iso : `${iso}Z`);
  const minutes = Math.round((Date.now() - at.getTime()) / 60_000);
  if (minutes < 1) return "just now";
  if (minutes < 60) return `${minutes} min ago`;
  const hours = Math.round(minutes / 60);
  if (hours < 24) return `${hours} h ago`;
  if (hours < 48) return "Yesterday";
  return at.toLocaleDateString(undefined, { month: "short", day: "numeric" });
}

// --------------------------------------------------------------------- pieces

function StatCard({ label, value, note }: { label: string; value: string; note?: string }) {
  return (
    <div className="rounded-xl border bg-card px-4 py-3">
      <div className="text-muted-foreground text-xs">{label}</div>
      <div className="mt-1 font-semibold text-2xl tabular-nums tracking-[-0.02em]">{value}</div>
      {note ? <div className="mt-1 truncate text-muted-foreground text-xs">{note}</div> : null}
    </div>
  );
}

function Signal({
  tone,
  label,
  children,
}: {
  tone: "warn" | "accent";
  label: string;
  children: React.ReactNode;
}) {
  const style =
    tone === "warn"
      ? { background: "var(--warn-wash)", color: "var(--warn-solid)" }
      : { background: "var(--accent-wash)", color: "var(--accent-text)" };
  return (
    <div className="flex items-center gap-2 text-sm">
      <span className="rounded px-1.5 py-0.5 font-medium text-[11px]" style={style}>
        {label}
      </span>
      <span>{children}</span>
    </div>
  );
}

function SetupProgress({ setup }: { setup: CourseProgress["setup"] }) {
  const done = setup.filter((step) => step.done).length;
  const next = setup.find((step) => !step.done)?.key;
  return (
    <div className="space-y-2">
      <div className="text-sm">
        <span className="font-medium">Setup</span>{" "}
        <span className="text-muted-foreground">
          {done} of {setup.length} steps done
        </span>
      </div>
      <div className="grid grid-cols-6 gap-1">
        {setup.map((step) => (
          <div key={step.key} className="space-y-1.5">
            <div
              className="h-1.5 rounded-full"
              style={{
                background: step.done
                  ? "var(--accent-solid)"
                  : step.key === next
                    ? "var(--warn-solid)"
                    : "var(--muted)",
              }}
            />
            <div className="truncate text-muted-foreground text-xs">{STEPS[step.key]?.label}</div>
          </div>
        ))}
      </div>
    </div>
  );
}

function CourseCard({
  progress,
  onSettings,
}: {
  progress: CourseProgress;
  onSettings: () => void;
}) {
  const { course } = progress;
  const next = progress.setup.find((step) => !step.done);
  const setupDone = next === undefined;
  // The list holds only courses you own (ADR-058), so an owner is named only for a
  // course someone else shares with you, which co-instructors will bring.
  const owner = progress.owned_by_you ? null : (progress.owner_email ?? null);

  const stats: Array<[string, string]> = [
    ["Books", String(course.book_count)],
    ["Taxonomies", String(course.curriculum_version_count)],
    ["Questions", course.question_count.toLocaleString()],
    ["Coverage", percent(progress.coverage)],
    ["Students", String(progress.student_count)],
    ["Avg. mastery", percent(progress.avg_mastery)],
  ];

  const signals: React.ReactNode[] = [];
  if (progress.awaiting_review_count > 0) {
    signals.push(
      <Signal key="review" tone="warn" label="Review">
        {plural(progress.awaiting_review_count, "question")} awaiting review
      </Signal>,
    );
  }
  if (progress.proposed_curriculum_count > 0) {
    signals.push(
      <Signal key="taxonomy" tone="warn" label="Taxonomy">
        {plural(progress.proposed_curriculum_count, "taxonomy", "taxonomies")} waiting for your
        approval
      </Signal>,
    );
  }

  return (
    // The whole card opens the course's dashboard: the name's button stretches over it
    // (`after:inset-0`), and the action buttons sit above that layer (`z-10`).
    <article className="relative overflow-hidden rounded-xl border bg-card transition-colors hover:border-primary/50 has-[button[data-open-course]:focus-visible]:ring-2 has-[button[data-open-course]:focus-visible]:ring-ring">
      <div className="space-y-4 p-5">
        <div className="flex flex-wrap items-start gap-3">
          <div className="min-w-0 flex-1">
            {course.description ? (
              <div className="truncate text-muted-foreground text-xs">{course.description}</div>
            ) : null}
            <h2 className="font-semibold text-lg tracking-[-0.01em]">
              <button
                type="button"
                data-open-course
                onClick={() => openCourse(course.id, "/dashboard")}
                className="text-left after:absolute after:inset-0 focus-visible:outline-none"
              >
                {course.name}
              </button>
            </h2>
            {owner ? <div className="text-muted-foreground text-sm">{owner}</div> : null}
          </div>
          <div className="relative z-10 flex gap-2">
            <Button variant="outline" size="sm" onClick={onSettings}>
              Settings
            </Button>
            <Button
              variant="outline"
              size="sm"
              onClick={() => openCourse(course.id, next ? STEPS[next.key]?.path : "/dashboard")}
            >
              {next ? `Continue: ${STEPS[next.key]?.action}` : "Open course"}
            </Button>
          </div>
        </div>

        {setupDone ? null : <SetupProgress setup={progress.setup} />}

        {progress.most_missed ? (
          <div className="text-muted-foreground text-xs">
            Most missed: {percent(progress.most_missed.miss_rate)} on{" "}
            <span className="text-foreground">{progress.most_missed.subtopic}</span> (
            {progress.most_missed.topic}, {plural(progress.most_missed.attempts, "answer")})
          </div>
        ) : null}
      </div>

      <dl className="grid grid-cols-3 gap-y-3 border-t px-5 py-3 sm:grid-cols-6">
        {stats.map(([label, value]) => (
          <div key={label}>
            <dt className="text-muted-foreground text-xs">{label}</dt>
            <dd className="font-medium tabular-nums">{value}</dd>
          </div>
        ))}
      </dl>

      {signals.length > 0 ? (
        <div className="space-y-1.5 border-t bg-muted/50 px-5 py-3">{signals}</div>
      ) : null}
    </article>
  );
}

function RecentActivity({ events }: { events: ActivityEvent[] }) {
  return (
    <section className="rounded-xl border bg-card p-5">
      <h2 className="font-semibold text-base">Recent activity</h2>
      {events.length === 0 ? (
        <p className="mt-3 text-muted-foreground text-sm">Nothing has happened yet.</p>
      ) : (
        <ul className="mt-3 space-y-4">
          {events.map((event) => (
            <li key={`${event.kind}-${event.at}-${event.text}`} className="wrap-anywhere text-sm">
              <div className="leading-5">{event.text}</div>
              <div className="mt-0.5 text-muted-foreground text-xs">
                {event.course_name ? `${event.course_name} · ` : ""}
                {timeAgo(event.at)}
              </div>
            </li>
          ))}
        </ul>
      )}
    </section>
  );
}

// -------------------------------------------------------------------- dialogs

/** Rename a course or change its description. Creating one is the New course page. */
function CourseFormDialog({
  course,
  onOpenChange,
}: {
  course: Schemas["CourseOut"];
  onOpenChange: (open: boolean) => void;
}) {
  const updateCourse = useUpdateCourse();
  const mutation = updateCourse;
  const nameId = useId();
  const descriptionId = useId();
  const [name, setName] = useState(course.name);
  const [description, setDescription] = useState(course.description ?? "");

  async function submit(event: React.FormEvent) {
    event.preventDefault();
    if (!name.trim()) return;
    const body = { name: name.trim(), description: description.trim() };
    try {
      await updateCourse.mutateAsync({ courseId: course.id, body });
      onOpenChange(false);
    } catch {
      // Rendered below with the backend's own message.
    }
  }

  return (
    <Dialog open onOpenChange={onOpenChange}>
      <DialogContent className="sm:max-w-md">
        <form onSubmit={submit} className="space-y-4">
          <DialogHeader>
            <DialogTitle>Course settings</DialogTitle>
            <DialogDescription>Rename the course or change its description.</DialogDescription>
          </DialogHeader>

          <div className="space-y-2">
            <Label htmlFor={nameId}>Name</Label>
            <Input
              id={nameId}
              value={name}
              maxLength={200}
              autoFocus
              placeholder="e.g. CS 135 · Intro to Programming"
              onChange={(event) => setName(event.target.value)}
            />
          </div>

          <div className="space-y-2">
            <Label htmlFor={descriptionId}>
              Description <span className="text-muted-foreground">(optional)</span>
            </Label>
            <Textarea
              id={descriptionId}
              value={description}
              maxLength={2000}
              className="h-[5rem]"
              placeholder="Term, section, who it is for…"
              onChange={(event) => setDescription(event.target.value)}
            />
          </div>

          {mutation.error ? <QueryError error={mutation.error} /> : null}

          <DialogFooter>
            <Button type="button" variant="ghost" onClick={() => onOpenChange(false)}>
              Cancel
            </Button>
            <Button type="submit" disabled={!name.trim() || mutation.isPending}>
              {mutation.isPending ? "Saving…" : "Save changes"}
            </Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  );
}

// --------------------------------------------------------------------- screen

/** My courses has no sidebar, so the account and sign-out live in its header. */
function SignOutButton() {
  const router = useRouter();
  const currentUser = useCurrentUser();
  const logout = useLogout();

  const signOut = async () => {
    await logout.mutateAsync();
    router.push("/login" as Route);
  };

  return (
    <>
      {currentUser.data?.email ? (
        <span className="text-muted-foreground text-sm">{currentUser.data.email}</span>
      ) : null}
      <Button variant="outline" disabled={logout.isPending} onClick={() => void signOut()}>
        <LogOut />
        Sign out
      </Button>
    </>
  );
}

export function CoursesScreen() {
  const overview = useCoursesOverview();
  // The course whose settings are open, if any.
  const [editing, setEditing] = useState<Schemas["CourseOut"] | null>(null);
  const [creating, setCreating] = useState(false);

  const courses = overview.data?.courses ?? [];
  const questions = courses.reduce((sum, c) => sum + c.course.question_count, 0);
  const approved = courses.reduce((sum, c) => sum + c.approved_question_count, 0);
  const awaiting = courses.reduce((sum, c) => sum + c.awaiting_review_count, 0);
  const students = courses.reduce((sum, c) => sum + c.student_count, 0);
  const awaitingByCourse = courses
    .filter((c) => c.awaiting_review_count > 0)
    .map((c) => `${c.awaiting_review_count} in ${c.course.name}`)
    .join(" · ");

  return (
    <div className="mx-auto flex min-h-screen w-full max-w-7xl flex-col gap-5 p-6">
      <header className="flex items-center gap-3">
        <h1 className="font-semibold text-2xl tracking-[-0.02em]">My courses</h1>
        <Button className="ml-auto" onClick={() => setCreating(true)}>
          <Plus />
          New course
        </Button>
        <SignOutButton />
      </header>

      <VerifyEmailBanner />

      {overview.isError ? <QueryError error={overview.error} /> : null}

      {overview.isPending ? (
        <div className="grid gap-4 lg:grid-cols-[minmax(0,1fr)_20rem]">
          <Skeleton className="h-72" />
          <Skeleton className="h-72" />
        </div>
      ) : null}

      {overview.data ? (
        <>
          <div className="grid gap-3 sm:grid-cols-3">
            <StatCard
              label="Questions"
              value={questions.toLocaleString()}
              note={`${approved.toLocaleString()} approved`}
            />
            <StatCard
              label="Awaiting review"
              value={awaiting.toLocaleString()}
              note={awaitingByCourse || "Nothing waiting"}
            />
            <StatCard
              label="Students"
              value={students.toLocaleString()}
              note={`across ${plural(courses.length, "course")}`}
            />
          </div>

          <div className="grid items-start gap-4 lg:grid-cols-[minmax(0,1fr)_20rem]">
            <div className="space-y-4">
              {courses.length === 0 ? (
                <div className="rounded-xl border border-dashed bg-card p-6">
                  <h2 className="font-semibold text-base">No courses yet</h2>
                  <p className="mt-1 text-muted-foreground text-sm">
                    Create your first course, then add its books and taxonomy.
                  </p>
                  <Button className="mt-4" onClick={() => setCreating(true)}>
                    <Plus />
                    New course
                  </Button>
                </div>
              ) : (
                courses.map((progress) => (
                  <CourseCard
                    key={progress.course.id}
                    progress={progress}
                    onSettings={() => setEditing(progress.course)}
                  />
                ))
              )}
            </div>
            <RecentActivity events={overview.data.activity} />
          </div>
        </>
      ) : null}

      {editing !== null ? (
        <CourseFormDialog course={editing} onOpenChange={() => setEditing(null)} />
      ) : null}
      {/* Mounted only while open, so each opening starts from a blank form. */}
      {creating ? <NewCourseDialog onOpenChange={setCreating} /> : null}
    </div>
  );
}
