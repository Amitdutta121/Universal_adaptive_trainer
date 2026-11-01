"use client";

/**
 * "Set up your course" on the course dashboard: the six steps from content to a student link,
 * each with its real state (`lib/course-setup.ts`) and one button that opens the screen that
 * already does the work. The next required step is highlighted. Once the classroom link exists
 * the checklist folds into a one-line "students can join" bar with the link.
 */

import { CheckCircle2, Circle, CircleDashed, Loader2 } from "lucide-react";
import Link from "next/link";
import { useEffect, useState } from "react";
import { toast } from "sonner";
import { CopyButton } from "@/components/copy-button";
import { QueryError } from "@/components/query-state";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import { readApiError } from "@/lib/api/client";
import { useSyncTaxonomyClassroom } from "@/lib/api/queries";
import { coursePath } from "@/lib/course";
import { type SetupStep, useCourseSetup } from "@/lib/course-setup";
import { cn } from "@/lib/utils";

function StepIcon({ step }: { step: SetupStep }) {
  if (step.state === "done") return <CheckCircle2 className="size-5 text-[var(--ok-solid)]" />;
  if (step.state === "running")
    return <Loader2 className="size-5 animate-spin text-[var(--warn-solid)]" />;
  if (step.state === "next") return <Circle className="size-5 text-primary" strokeWidth={2.5} />;
  return <CircleDashed className="size-5 text-muted-foreground" />;
}

function useOrigin() {
  const [origin, setOrigin] = useState("");
  useEffect(() => setOrigin(window.location.origin), []);
  return origin;
}

export function SetupChecklist({ courseId }: { courseId: number }) {
  const { setup, error } = useCourseSetup(courseId);
  const createLink = useSyncTaxonomyClassroom();
  const [expanded, setExpanded] = useState(false);
  const origin = useOrigin();

  if (error) return <QueryError error={error} />;
  if (!setup) return <Skeleton className="h-64 w-full rounded-2xl" data-testid="setup-loading" />;

  const link =
    origin && setup.curriculumVersionId !== null
      ? `${origin}/students/join?taxonomy=${setup.curriculumVersionId}`
      : "";

  async function onCreateLink() {
    if (setup?.curriculumVersionId == null) return;
    try {
      await createLink.mutateAsync(setup.curriculumVersionId);
      toast.success("Student link created");
    } catch (caught) {
      toast.error(readApiError(caught)?.message ?? "Could not create the link");
    }
  }

  if (setup.live && !expanded) {
    return (
      <Card className="border" data-testid="setup-live">
        <CardContent className="flex flex-wrap items-center justify-between gap-3 py-3">
          <div className="flex min-w-0 flex-wrap items-center gap-3">
            <Badge className="bg-[var(--ok-wash)] text-[var(--ok-solid)]">Live</Badge>
            <span className="text-sm">Students join at</span>
            <code className="min-w-0 truncate font-mono text-sm">{link}</code>
          </div>
          <div className="flex gap-2">
            <CopyButton text={link} label="Copy link" copiedLabel="Copied" size="sm" />
            <Button variant="ghost" size="sm" onClick={() => setExpanded(true)}>
              Setup checklist
            </Button>
          </div>
        </CardContent>
      </Card>
    );
  }

  return (
    <Card className="border" data-testid="setup-checklist">
      <CardHeader className="flex flex-row flex-wrap items-start justify-between gap-3">
        <div className="space-y-1">
          <CardTitle className="text-base">Set up your course</CardTitle>
          <CardDescription>
            {setup.done} of {setup.total} done
            {setup.next ? ` · next: ${setup.next.title.toLowerCase()}` : ""}
          </CardDescription>
        </div>
        <div className="flex items-center gap-1" aria-hidden="true">
          {setup.steps
            .filter((step) => !step.optional)
            .map((step) => (
              <span
                key={step.key}
                className={cn(
                  "h-1.5 w-7 rounded-full bg-muted",
                  step.state === "done" && "bg-[var(--ok-solid)]",
                  step === setup.next && "bg-primary",
                )}
              />
            ))}
        </div>
        {setup.live ? (
          <Button variant="ghost" size="sm" onClick={() => setExpanded(false)}>
            Hide
          </Button>
        ) : null}
      </CardHeader>
      <CardContent className="p-0">
        {setup.otherLive.length > 0 ? (
          <p
            className="border-t px-6 py-2 text-muted-foreground text-sm"
            data-testid="setup-other-live"
          >
            Students can still join {setup.otherLive.map((entry) => `“${entry.label}”`).join(", ")}{" "}
            with {setup.otherLive.length === 1 ? "its link" : "their links"}; this checklist is for
            the taxonomy selected now.
          </p>
        ) : null}
        <ol>
          {setup.steps.map((step) => {
            const isNext = step === setup.next;
            const shareNow =
              step.key === "share" && step.state !== "done" && step.state !== "blocked";
            return (
              <li
                key={step.key}
                data-step={step.key}
                data-state={step.state}
                className={cn(
                  "grid grid-cols-[1.25rem_minmax(0,1fr)_auto] items-center gap-4 border-t px-6 py-3",
                  isNext && "bg-accent/50",
                )}
              >
                <StepIcon step={step} />
                <div className="min-w-0">
                  <div
                    className={cn(
                      "font-medium text-sm",
                      step.state === "blocked" && "text-muted-foreground",
                    )}
                  >
                    {step.title}
                  </div>
                  <div className="truncate text-muted-foreground text-sm" title={step.detail}>
                    {step.detail}
                  </div>
                </div>
                <div className="flex flex-wrap items-center justify-end gap-2">
                  {step.key === "share" && step.state === "done" ? (
                    <CopyButton text={link} label="Copy link" copiedLabel="Copied" size="sm" />
                  ) : shareNow ? (
                    <Button
                      size="sm"
                      variant={isNext ? "default" : "outline"}
                      onClick={onCreateLink}
                      disabled={createLink.isPending}
                    >
                      {createLink.isPending ? "Creating…" : step.action}
                    </Button>
                  ) : step.state === "blocked" ? null : (
                    <Button asChild size="sm" variant={isNext ? "default" : "ghost"}>
                      <Link href={coursePath(courseId, step.path)}>
                        {step.state === "done" ? "Open" : step.action}
                      </Link>
                    </Button>
                  )}
                </div>
              </li>
            );
          })}
        </ol>
      </CardContent>
    </Card>
  );
}
