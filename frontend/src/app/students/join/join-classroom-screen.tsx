"use client";

import { ArrowRight, Link as LinkIcon, RotateCcw, Target, TrendingUp } from "lucide-react";
import type { Route } from "next";
import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";
import { useEffect, useMemo, useState } from "react";
import { PageHeader } from "@/components/page-header";
import { EmptyState, QueryError } from "@/components/query-state";
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { useCreateStudent, useQuestionSet, useStartTrainingSession } from "@/lib/api/queries";

// Local, per-browser convenience only -- not an identity mechanism. Students
// have no accounts (ADR-041), so this just saves retyping a name on the same
// device; it plays no part in the "names must be unique" rule the backend
// enforces.
const LEARNER_NAME_STORAGE_KEY = "adaptive-trainer:learner-name";

// Landing page for a classroom link (`/students/join?set=<id>`): shows what
// the frozen set contains, then creates a new learner and training session
// and hands off to the session screen.
export function JoinClassroomScreen() {
  const router = useRouter();
  const searchParams = useSearchParams();
  const rawSetId = searchParams.get("set");
  // A missing or non-numeric `set` query param renders as a broken-link
  // state below rather than a query error, since there is no id to query with.
  const setVersionId = useMemo(() => {
    const parsed = Number(rawSetId);
    return Number.isInteger(parsed) && parsed > 0 ? parsed : null;
  }, [rawSetId]);

  const classroom = useQuestionSet(setVersionId ?? 0, { enabled: setVersionId !== null });
  const createStudent = useCreateStudent();
  const startTrainingSession = useStartTrainingSession();

  const [displayName, setDisplayName] = useState("");

  // Prefill from whatever name was last used successfully on this device.
  useEffect(() => {
    const remembered = window.localStorage.getItem(LEARNER_NAME_STORAGE_KEY);
    if (remembered) setDisplayName(remembered);
  }, []);

  const joinClassroom = async () => {
    if (setVersionId === null) return;
    const trimmed = displayName.trim();
    if (!trimmed) return;

    try {
      // Every join creates a fresh student row -- there is no "log back in as
      // an existing learner" here, so a name collision (handled by
      // createStudent.isError below) is the backend's uniqueness rule doing
      // its job, not a bug.
      const learner = await createStudent.mutateAsync({ display_name: trimmed });
      const session = await startTrainingSession.mutateAsync({
        student_id: learner.id,
        set_version_id: setVersionId,
      });
      // Only remember the name once both calls actually succeeded.
      window.localStorage.setItem(LEARNER_NAME_STORAGE_KEY, trimmed);
      router.push(`/students/join/session/${session.id}` as Route);
    } catch {
      // Mutation state already carries the backend error for rendering.
    }
  };

  return (
    <>
      {/* No sidebar trigger (students have no console nav) and no taxonomy
          selector (a professor-only control with no meaning here -- and it
          can change the app's active curriculum, so it must never appear on
          a page a student can reach). */}
      <PageHeader
        title="Join classroom"
        summary="Enter your learner name to start an adaptive training session from this frozen question set."
        showSidebarTrigger={false}
        showTaxonomySelector={false}
      />

      {setVersionId === null ? (
        <EmptyState
          title="This classroom link is incomplete"
          hint="The join URL must include a valid frozen set id."
        />
      ) : null}

      {setVersionId !== null && classroom.isError ? <QueryError error={classroom.error} /> : null}

      {setVersionId !== null && classroom.data ? (
        <div className="mx-auto grid w-full max-w-4xl gap-4 lg:grid-cols-[1.1fr_0.9fr]">
          <Card className="border-border/70">
            <CardHeader className="gap-3">
              <div className="flex items-center gap-2 text-muted-foreground text-xs uppercase tracking-[0.18em]">
                <LinkIcon className="size-3.5" />
                Classroom snapshot
              </div>
              <CardTitle className="text-2xl">{classroom.data.label}</CardTitle>
            </CardHeader>
            <CardContent className="space-y-4">
              <div className="flex flex-wrap gap-2">
                <Badge variant="outline">Set #{classroom.data.id}</Badge>
                <Badge variant="outline">{classroom.data.member_count} questions</Badge>
                <Badge variant="outline">
                  Frozen{" "}
                  {new Intl.DateTimeFormat(undefined, { dateStyle: "medium" }).format(
                    new Date(classroom.data.created_at),
                  )}
                </Badge>
              </div>

              {classroom.data.notes ? (
                <Alert>
                  <ArrowRight />
                  <AlertTitle>Professor notes</AlertTitle>
                  <AlertDescription>{classroom.data.notes}</AlertDescription>
                </Alert>
              ) : null}

              <p className="text-muted-foreground text-sm leading-6">
                This classroom always uses the exact question snapshot the professor froze for it,
                so everyone joining later is still training against the same set.
              </p>

              {/* Short, plain-language restatement of the fixed adaptive-training
                  rules in CLAUDE.md (weakness-weighted roulette, BKT-driven
                  difficulty, low-priority reuse) so a student knows what to
                  expect before their first question. */}
              <div className="space-y-3 border-t border-border/60 pt-4">
                <div className="font-medium text-foreground text-sm">
                  How this training adapts to you
                </div>
                <ul className="space-y-3 text-sm leading-6">
                  <li className="flex items-start gap-2.5">
                    <Target className="mt-0.5 size-4 shrink-0 text-primary" />
                    <span>Questions favor the subtopics you're weakest in.</span>
                  </li>
                  <li className="flex items-start gap-2.5">
                    <TrendingUp className="mt-0.5 size-4 shrink-0 text-primary" />
                    <span>Difficulty follows your measured mastery, topic by topic.</span>
                  </li>
                  <li className="flex items-start gap-2.5">
                    <RotateCcw className="mt-0.5 size-4 shrink-0 text-primary" />
                    <span>A used question resurfaces only after others have had a turn.</span>
                  </li>
                </ul>
              </div>
            </CardContent>
          </Card>

          <Card className="border-border/70">
            <CardHeader>
              <CardTitle className="text-xl">Start learning</CardTitle>
            </CardHeader>
            <CardContent className="space-y-4">
              <div className="space-y-2">
                <label className="font-medium text-sm" htmlFor="learner-name">
                  Learner name
                </label>
                <Input
                  id="learner-name"
                  value={displayName}
                  onChange={(event) => setDisplayName(event.target.value)}
                  maxLength={200}
                  placeholder="e.g. Ada Lovelace"
                  onKeyDown={(event) => {
                    if (event.key === "Enter") {
                      event.preventDefault();
                      void joinClassroom();
                    }
                  }}
                />
                <p className="text-muted-foreground text-sm">
                  Names must be unique. If someone already used yours, add an initial or cohort tag.
                </p>
              </div>

              {createStudent.isError ? <QueryError error={createStudent.error} /> : null}
              {startTrainingSession.isError ? (
                <QueryError error={startTrainingSession.error} />
              ) : null}

              <Button
                type="button"
                className="w-full"
                disabled={
                  displayName.trim().length === 0 ||
                  createStudent.isPending ||
                  startTrainingSession.isPending
                }
                onClick={() => void joinClassroom()}
              >
                <ArrowRight />
                Start adaptive session
              </Button>

              <p className="text-center text-muted-foreground text-xs">
                Professor console: <Link href="/students">manage classrooms and learners</Link>
              </p>
            </CardContent>
          </Card>
        </div>
      ) : null}
    </>
  );
}
