/**
 * The course setup checklist: what a professor still has to do before students can join.
 *
 * Every step's state is read from what the backend already enforces, never from clicks:
 *   1. Content       — a book or video exists. An import runs as a background job and writes
 *                      the row only once it succeeds, so a running or failed import job is
 *                      what the step shows meanwhile.
 *   2. Curriculum    — the course has an approved taxonomy. Drafting reads no book (ADR-052),
 *                      so it does not wait for content.
 *   3. Question types — a question setup is saved for that taxonomy; saving starts round 1.
 *   4. Review        — the taxonomy has at least one approved question, because creating its
 *                      classroom link freezes the approved questions and refuses an empty set.
 *   5. Tutorials     — optional: with live tutorials on, library recipes reach students as
 *                      they pass their checks, so a decision is only needed for the course's own.
 *   6. Share         — the taxonomy's classroom link exists. It is a live set: questions
 *                      approved later reach students without re-creating the link.
 *
 * `deriveSetup` is pure so the states can be tested without a server; `useCourseSetup` feeds it.
 */

import { useQueryClient } from "@tanstack/react-query";
import { useEffect } from "react";
import {
  qk,
  useApprovedCurriculum,
  useAssessmentCatalog,
  useBooks,
  useCourse,
  useCurrentSetup,
  useCurriculumVersions,
  useJobs,
  useRound,
  useTaxonomyLinks,
  useTutorialRecipes,
} from "@/lib/api/queries";
import type { Schemas } from "@/lib/api/types";

export type StepKey = "content" | "curriculum" | "questions" | "review" | "tutorials" | "share";

/** `running` is a step whose work is happening in the background; `blocked` names its reason. */
export type StepState = "done" | "next" | "running" | "todo" | "blocked" | "optional";

export interface SetupStep {
  key: StepKey;
  title: string;
  state: StepState;
  /** One line: what was done, what is happening, or what is needed. */
  detail: string;
  /** Relative to the open course. */
  path: string;
  /** The button for the step that is next. */
  action: string;
  optional?: boolean;
}

export interface SetupInputs {
  books: Schemas["BookListResponse"] | undefined;
  versions: Schemas["CurriculumListResponse"] | undefined;
  /** `null` when the course has no approved taxonomy (the endpoint answers 404). */
  approved: Schemas["CurriculumVersionDetail"] | null;
  setup: Schemas["QuestionSetupOut"] | null;
  link: Schemas["TaxonomyLinkOut"] | null;
  /** Every taxonomy link of the course; links of other taxonomies keep serving students. */
  allLinks?: Schemas["TaxonomyLinkOut"][];
  recipes: Schemas["TutorialRecipeListResponse"] | undefined;
  /** This course's book-import jobs, newest first (`GET /api/jobs`). */
  imports?: Schemas["JobOut"][];
  /** The course's subject, when it has no question style library (catalog `ready: false`):
   * question setup refuses such a course, so the step says why instead. */
  subjectWithoutStyles?: string | null;
}

export interface CourseSetup {
  steps: SetupStep[];
  /** Required steps done, out of `total` required: what "3 of 5" counts. Tutorials are optional
   * and not counted, as in the course list's setup (`app/courses/overview.py`). */
  done: number;
  total: number;
  /** The first required step not done; `null` once students can join. */
  next: SetupStep | null;
  /** Students can join: the classroom link exists. */
  live: boolean;
  curriculumVersionId: number | null;
  /** Other taxonomies whose classroom link is live: still joinable after a new one is chosen. */
  otherLive: { curriculumVersionId: number; label: string }[];
}

const ACTIVE_ROUND = new Set(["queued", "running"]);

function plural(count: number, one: string, many = `${one}s`) {
  return `${count} ${count === 1 ? one : many}`;
}

export function deriveSetup(input: SetupInputs): CourseSetup {
  const { books, versions, approved, setup, link, recipes, imports = [] } = input;
  const bookCount = books?.total ?? 0;
  const importing = imports.filter((job) => ACTIVE_ROUND.has(job.status));
  const failedImport = imports.find((job) => job.status === "failed") ?? null;
  const approvedQuestions = link?.approved_question_count ?? 0;
  const round = setup?.latest_round ?? null;
  const roundActive = round !== null && ACTIVE_ROUND.has(round.status);
  const draft = versions?.versions.find(
    (version) => version.status === "proposed" || version.status === "under_review",
  );

  const content: SetupStep = {
    key: "content",
    title: "Add course content",
    path: "/books",
    action: "Upload content",
    state: bookCount > 0 ? "done" : importing.length > 0 ? "running" : "todo",
    detail:
      bookCount > 0
        ? `${plural(bookCount, "item")}: ${books?.books
            .slice(0, 2)
            .map((book) => book.title)
            .join(", ")}${bookCount > 2 ? ", …" : ""}${
            importing.length > 0 ? ` · importing ${importing.length} more` : ""
          }`
        : importing.length > 0
          ? `Importing ${importing.map((job) => job.title.replace(/^Import book · /, "")).join(", ")}`
          : failedImport
            ? `Import failed${failedImport.error ? `: ${failedImport.error}` : ""}`
            : "Upload a textbook PDF, slides or a lecture video",
  };

  const curriculum: SetupStep = {
    key: "curriculum",
    title: "Approve the curriculum",
    path: "/curriculum",
    action: draft ? "Review the draft" : "Build the curriculum",
    state: approved ? "done" : "todo",
    detail: approved
      ? `${approved.version.label} · ${plural(approved.topic_count, "topic")} · ${plural(
          approved.subtopic_count,
          "subtopic",
        )}`
      : draft
        ? `Draft "${draft.label}" is waiting for your approval`
        : "Draft it with AI from a course description, or import your own",
  };

  const styleCount = new Set(setup?.approved_styles.flatMap((entry) => entry.style_ids)).size;
  const target = setup?.cell_targets.reduce((sum, cell) => sum + cell.target, 0) ?? 0;
  const questions: SetupStep = {
    key: "questions",
    title: "Choose question types",
    path: "/questions",
    action: "Set up questions",
    state: setup ? "done" : approved && !input.subjectWithoutStyles ? "todo" : "blocked",
    detail: setup
      ? `${plural(styleCount, "question style")} · ${plural(target, "target question")}`
      : input.subjectWithoutStyles
        ? `No question styles for ${input.subjectWithoutStyles} yet`
        : approved
          ? "Pick the question styles for each subtopic; the AI suggests them"
          : "Needs an approved curriculum",
  };

  let reviewState: StepState;
  let reviewDetail: string;
  if (approvedQuestions > 0) {
    reviewState = "done";
    reviewDetail = `${plural(approvedQuestions, "approved question")}${
      roundActive ? ` · round ${round?.number} writing more` : ""
    }`;
  } else if (roundActive && round) {
    reviewState = "running";
    reviewDetail = `Round ${round.number} is writing questions: ${round.produced} of ${round.requested}`;
  } else if (round?.status === "failed") {
    reviewState = "todo";
    reviewDetail = `Round ${round.number} failed${round.error ? `: ${round.error}` : ""}`;
  } else if (setup) {
    reviewState = "todo";
    reviewDetail = "Approve at least one question in the Review Queue";
  } else {
    reviewState = "blocked";
    reviewDetail = "Starts after question types";
  }
  const review: SetupStep = {
    key: "review",
    title: "Review the first questions",
    path: "/review",
    action: "Open the Review Queue",
    state: reviewState,
    detail: reviewDetail,
  };

  const decided = Object.keys(recipes?.decisions ?? {}).length;
  const tutorials: SetupStep = {
    key: "tutorials",
    title: "Approve tutorial styles",
    path: "/tutorials",
    action: "Review tutorial styles",
    optional: true,
    state: !approved ? "blocked" : decided > 0 ? "done" : "optional",
    detail: !approved
      ? "Needs an approved curriculum"
      : decided > 0
        ? `${plural(decided, "decision")} on ${plural(recipes?.recipes.length ?? 0, "style")}`
        : recipes?.live
          ? "Optional · live tutorials use the library styles as students need them"
          : "Optional · choose how tutorials teach when a student is stuck",
  };

  const classroom = link?.classroom ?? null;
  const share: SetupStep = {
    key: "share",
    title: "Share with students",
    path: "/students",
    action: "Create student link",
    state: classroom ? "done" : approvedQuestions > 0 ? "todo" : "blocked",
    detail: classroom
      ? "Students can join · questions you approve later reach them automatically"
      : approvedQuestions > 0
        ? `Create the link for ${plural(approvedQuestions, "approved question")}`
        : "Needs at least one approved question",
  };

  const steps = [content, curriculum, questions, review, tutorials, share];
  const next = steps.find((step) => !step.optional && step.state !== "done") ?? null;
  if (next && next.state !== "running") next.state = "next";
  return {
    steps,
    done: steps.filter((step) => !step.optional && step.state === "done").length,
    total: steps.filter((step) => !step.optional).length,
    next,
    live: classroom !== null,
    curriculumVersionId: approved?.version.id ?? null,
    otherLive: (input.allLinks ?? [])
      .filter((entry) => entry.classroom && entry.curriculum_version_id !== approved?.version.id)
      .map((entry) => ({ curriculumVersionId: entry.curriculum_version_id, label: entry.label })),
  };
}

/**
 * The checklist for the open course, or `null` while its queries load. Polls while a round is
 * writing questions so the review step moves without a reload.
 */
export function useCourseSetup(courseId: number): { setup: CourseSetup | null; error: unknown } {
  const course = useCourse(courseId);
  const catalog = useAssessmentCatalog();
  const books = useBooks();
  const versions = useCurriculumVersions();
  const approved = useApprovedCurriculum();
  const versionId = approved.data?.version.id ?? null;
  const current = useCurrentSetup(versionId);
  const links = useTaxonomyLinks();
  const recipes = useTutorialRecipes(versionId);
  const jobs = useJobs();
  const imports = (jobs.data?.jobs ?? []).filter((job) => job.kind === "book_import");
  const importsActive = imports.filter((job) => ACTIVE_ROUND.has(job.status)).length;
  const latest = current.data?.setup?.latest_round ?? null;
  // `useRound` polls until the round is done or failed; each new question may be auto-approved,
  // so the approved count behind steps 4 and 6 is refetched as the round moves.
  const round = useRound(latest && ACTIVE_ROUND.has(latest.status) ? latest.id : null);
  const client = useQueryClient();
  const progress = round.data ? `${round.data.status}:${round.data.produced}` : null;
  useEffect(() => {
    if (progress === null) return;
    client.invalidateQueries({ queryKey: qk.questionSets.taxonomyLinks() });
    if (!progress.startsWith("queued") && !progress.startsWith("running")) {
      client.invalidateQueries({ queryKey: qk.setup.all });
    }
  }, [client, progress]);
  // A finished import writes the book row; refetch the list when the active count drops.
  useEffect(() => {
    if (importsActive === 0) client.invalidateQueries({ queryKey: qk.books.all });
  }, [client, importsActive]);

  const pending =
    course.isPending ||
    catalog.isPending ||
    books.isPending ||
    versions.isPending ||
    approved.isPending ||
    links.isPending ||
    (versionId !== null && (current.isPending || recipes.isPending));
  const error = books.error ?? versions.error ?? links.error ?? null;
  if (pending || error) return { setup: null, error };

  return {
    setup: deriveSetup({
      books: books.data,
      versions: versions.data,
      // The endpoint answers 404 when nothing is approved; every screen reads that as "none".
      approved: approved.data ?? null,
      setup: current.data?.setup
        ? { ...current.data.setup, latest_round: round.data ?? latest }
        : null,
      link: links.data?.links.find((entry) => entry.curriculum_version_id === versionId) ?? null,
      allLinks: links.data?.links,
      recipes: recipes.data,
      imports,
      subjectWithoutStyles: (() => {
        const subject = catalog.data?.subjects.find(
          (entry) => entry.id === (course.data?.subject ?? "intro_python"),
        );
        return subject && !subject.ready ? subject.label : null;
      })(),
    }),
    error: null,
  };
}
