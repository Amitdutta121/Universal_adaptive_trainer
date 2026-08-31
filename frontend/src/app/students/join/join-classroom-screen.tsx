"use client";

import { ArrowRight, Link as LinkIcon, RotateCcw, Target, TrendingUp } from "lucide-react";
import type { Route } from "next";
import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";
import { useEffect, useMemo, useRef, useState } from "react";
import { PageHeader } from "@/components/page-header";
import { EmptyState, QueryError } from "@/components/query-state";
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { readApiError } from "@/lib/api/client";
import {
  useCreateStudent,
  useProdQuestionSet,
  useQuestionSet,
  useResumeStudent,
  useStartTrainingSession,
} from "@/lib/api/queries";
import {
  clearLearnerIdentity,
  type LearnerIdentity,
  loadLearnerIdentity,
  rememberedLearnerEmail,
  rememberedLearnerName,
  saveLearnerIdentity,
} from "./learner-identity";

// A deliberately loose client-side check: something@something.tld. The backend's
// EmailStr is the real gate; this only stops an obviously-incomplete submit.
const LOOKS_LIKE_EMAIL = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;

// Landing page for a classroom link (`/students/join?set=<id>`). A first-time
// visitor enrols and starts a run; a returning browser is recognised by the
// resume token it stored last time (ADR-041) and is offered its in-progress
// session instead of a name field that the uniqueness rule would reject.
export function JoinClassroomScreen() {
  const router = useRouter();
  const searchParams = useSearchParams();
  const rawSetId = searchParams.get("set");
  const isProdLink = rawSetId === "prod";
  // A missing or non-numeric `set` query param renders as a broken-link
  // state below rather than a query error, since there is no id to query with.
  const explicitSetVersionId = useMemo(() => {
    const parsed = Number(rawSetId);
    return Number.isInteger(parsed) && parsed > 0 ? parsed : null;
  }, [rawSetId]);

  const frozenClassroom = useQuestionSet(explicitSetVersionId ?? 0, {
    enabled: explicitSetVersionId !== null,
  });
  const prodClassroom = useProdQuestionSet({ enabled: isProdLink });
  const classroom = isProdLink ? prodClassroom : frozenClassroom;
  const createStudent = useCreateStudent();
  const startTrainingSession = useStartTrainingSession();
  const resumeStudent = useResumeStudent();

  const [displayName, setDisplayName] = useState("");
  const [email, setEmail] = useState("");
  const [identity, setIdentity] = useState<LearnerIdentity | null>(null);
  const resolvedSetVersionId = classroom.data?.id ?? explicitSetVersionId;

  // Read the per-browser identity once, on the client. Prefill the name and
  // email fields from it (or the legacy name-only key) for a visitor who has no
  // identity.
  useEffect(() => {
    setIdentity(loadLearnerIdentity());
    setDisplayName(rememberedLearnerName());
    setEmail(rememberedLearnerEmail());
  }, []);

  // As soon as both the stored identity and the classroom id are known, ask the
  // backend who the token belongs to and whether a run is still open. Runs once
  // per mount; a 404 means the token outlived its database, so it is dropped and
  // the enrol form takes over.
  const resumeRequested = useRef(false);
  // biome-ignore lint/correctness/useExhaustiveDependencies: fire once when both inputs are ready
  useEffect(() => {
    if (!identity || resolvedSetVersionId === null || resumeRequested.current) return;
    resumeRequested.current = true;
    resumeStudent.mutate(
      { resume_token: identity.resumeToken, set_version_id: resolvedSetVersionId },
      {
        onError: (error) => {
          if (readApiError(error)?.status === 404) {
            clearLearnerIdentity();
            setIdentity(null);
          }
        },
      },
    );
  }, [identity, resolvedSetVersionId]);

  const forgetIdentity = () => {
    clearLearnerIdentity();
    setIdentity(null);
    resumeStudent.reset();
    setDisplayName("");
    setEmail("");
  };

  const trimmedName = displayName.trim();
  const trimmedEmail = email.trim();
  const enrolReady = trimmedName.length > 0 && LOOKS_LIKE_EMAIL.test(trimmedEmail);

  const joinClassroom = async () => {
    if (resolvedSetVersionId === null || !enrolReady) return;

    try {
      // A first enrol still creates a fresh student row; a name collision
      // (surfaced by createStudent.isError below) is the uniqueness rule working,
      // and the returning-learner path above is how a student avoids hitting it.
      const learner = await createStudent.mutateAsync({
        display_name: trimmedName,
        email: trimmedEmail,
      });
      const session = await startTrainingSession.mutateAsync({
        student_id: learner.id,
        set_version_id: resolvedSetVersionId,
      });
      // Only store the identity once both calls actually succeeded.
      saveLearnerIdentity({
        studentId: learner.id,
        resumeToken: learner.resume_token,
        displayName: trimmedName,
        email: trimmedEmail,
      });
      router.push(`/students/join/session/${session.id}` as Route);
    } catch {
      // Mutation state already carries the backend error for rendering.
    }
  };

  // Start a new run for an already-known learner, keeping their measured state.
  const continueAsIdentity = async () => {
    if (resolvedSetVersionId === null || !identity) return;
    try {
      const session = await startTrainingSession.mutateAsync({
        student_id: identity.studentId,
        set_version_id: resolvedSetVersionId,
      });
      router.push(`/students/join/session/${session.id}` as Route);
    } catch (error) {
      // The one-active-session guard (409): a stale tab or a race already opened
      // a run. Re-resolve it and send the learner there rather than leaving them
      // on a dead button.
      if (readApiError(error)?.code === "active_session_exists") {
        try {
          const fresh = await resumeStudent.mutateAsync({
            resume_token: identity.resumeToken,
            set_version_id: resolvedSetVersionId,
          });
          if (fresh.active_session) {
            router.push(`/students/join/session/${fresh.active_session.id}` as Route);
            return;
          }
        } catch {
          // fall through to the rendered error
        }
      }
      // startTrainingSession.isError is rendered below.
    }
  };

  const resumed = resumeStudent.data;
  const activeSession = resumed?.active_session ?? null;
  const activeSessionElsewhere =
    activeSession !== null && activeSession.set_version_id !== resolvedSetVersionId;

  return (
    <>
      {/* No sidebar trigger (students have no console nav) and no taxonomy
          selector (a professor-only control with no meaning here -- and it
          can change the app's active curriculum, so it must never appear on
          a page a student can reach). */}
      <PageHeader
        title="Join classroom"
        summary="Start — or pick up — an adaptive training session from this classroom snapshot."
        showSidebarTrigger={false}
        showTaxonomySelector={false}
      />

      {rawSetId === null || (!isProdLink && explicitSetVersionId === null) ? (
        <EmptyState
          title="This classroom link is incomplete"
          hint="The join URL must include a valid classroom id."
        />
      ) : null}

      {(isProdLink || explicitSetVersionId !== null) && classroom.isError ? (
        <QueryError error={classroom.error} />
      ) : null}

      {(isProdLink || explicitSetVersionId !== null) && classroom.data ? (
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
                {isProdLink ? <Badge>Current prod classroom</Badge> : null}
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
                {isProdLink
                  ? "This link always opens the professor's current production classroom snapshot."
                  : "This classroom always uses the exact question snapshot the professor froze for it, so everyone joining later is still training against the same set."}
              </p>

              {/* Short, plain-language restatement of the adaptive rules
                  (weakness-weighted roulette, BKT-driven difficulty,
                  low-priority reuse) so a student knows what to expect before
                  their first question. */}
              <div className="space-y-3 border-border/60 border-t pt-4">
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
              <CardTitle className="text-xl">{identity ? "Welcome back" : "Start learning"}</CardTitle>
            </CardHeader>
            <CardContent className="space-y-4">
              {identity ? (
                <div className="space-y-4">
                  {resumeStudent.isPending ? (
                    <p className="text-muted-foreground text-sm">Checking your saved progress…</p>
                  ) : resumed ? (
                    <>
                      <p className="text-sm leading-6">
                        You're training as{" "}
                        <span className="font-medium text-foreground">
                          {resumed.student.display_name}
                        </span>
                        {activeSession
                          ? activeSessionElsewhere
                            ? ` and have a session in progress in ${
                                activeSession.set_label ?? "another classroom"
                              }. You can run only one at a time.`
                            : " and have a session in progress on this classroom."
                          : ". Your measured mastery carries over to a new session."}
                      </p>

                      {startTrainingSession.isError ? (
                        <QueryError error={startTrainingSession.error} />
                      ) : null}

                      {activeSession ? (
                        <Button
                          type="button"
                          className="w-full"
                          onClick={() =>
                            router.push(
                              `/students/join/session/${activeSession.id}` as Route,
                            )
                          }
                        >
                          <ArrowRight />
                          Resume session
                        </Button>
                      ) : (
                        <Button
                          type="button"
                          className="w-full"
                          disabled={startTrainingSession.isPending}
                          onClick={() => void continueAsIdentity()}
                        >
                          <ArrowRight />
                          Continue training
                        </Button>
                      )}
                    </>
                  ) : (
                    <QueryError error={resumeStudent.error} />
                  )}

                  <button
                    type="button"
                    className="text-muted-foreground text-xs underline underline-offset-4 hover:text-foreground"
                    onClick={forgetIdentity}
                  >
                    Not {identity.displayName}? Use a different name
                  </button>
                </div>
              ) : (
                <>
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
                      Names must be unique. If someone already used yours, add an initial or cohort
                      tag.
                    </p>
                  </div>

                  <div className="space-y-2">
                    <label className="font-medium text-sm" htmlFor="learner-email">
                      Email
                    </label>
                    <Input
                      id="learner-email"
                      type="email"
                      autoComplete="email"
                      value={email}
                      onChange={(event) => setEmail(event.target.value)}
                      maxLength={320}
                      placeholder="you@school.edu"
                      onKeyDown={(event) => {
                        if (event.key === "Enter") {
                          event.preventDefault();
                          void joinClassroom();
                        }
                      }}
                    />
                    <p className="text-muted-foreground text-sm">
                      So your instructor can reach you about your progress.
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
                      !enrolReady || createStudent.isPending || startTrainingSession.isPending
                    }
                    onClick={() => void joinClassroom()}
                  >
                    <ArrowRight />
                    Start adaptive session
                  </Button>
                </>
              )}

              <p className="text-center text-muted-foreground text-xs">
                Instructor Studio: <Link href="/students">manage classrooms and learners</Link>
              </p>
            </CardContent>
          </Card>
        </div>
      ) : null}
    </>
  );
}
