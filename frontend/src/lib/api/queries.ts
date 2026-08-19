/**
 * Query keys and typed hooks over the backend API.
 *
 * Server state (anything the backend owns) lives here and nowhere else. React state
 * is reserved for what the browser genuinely owns — an open dialog, an unsaved form,
 * a code buffer being typed.
 *
 * Keys are built by the factory below so that an invalidation can name a whole
 * subtree (`qk.questions.all`) without a caller guessing at the shape of a key.
 */

import {
  keepPreviousData,
  queryOptions,
  useMutation,
  useQueries,
  useQuery,
  useQueryClient,
} from "@tanstack/react-query";
import { API_BASE_URL } from "@/lib/env";
import { ApiError, api, unwrap } from "./client";
import type { QuestionStatus, QuestionType, Schemas, TypeInstructionListResponse } from "./types";

type ChunkGenerationSpec = Schemas["ChunkGenerationSpec"];

/** The query key factory. Every key in the app starts here. */
export const qk = {
  system: {
    health: () => ["system", "health"] as const,
    config: () => ["system", "config"] as const,
    counts: () => ["system", "counts"] as const,
  },
  questions: {
    all: ["questions"] as const,
    list: (params: { limit?: number; status?: QuestionStatus }) =>
      ["questions", "list", params] as const,
    detail: (id: number) => ["questions", "detail", id] as const,
    evaluations: (id: number) => ["questions", "evaluations", id] as const,
    reviewQueue: (params: { mode: "all" | "scoreable"; after?: number | null }) =>
      ["questions", "review-queue", params] as const,
    generationPlan: (bookId: number) => ["questions", "generation-plan", bookId] as const,
    batchPlan: (chunks: readonly ChunkGenerationSpec[]) =>
      ["questions", "batch-plan", chunks] as const,
  },
  books: {
    all: ["books"] as const,
    list: () => ["books", "list"] as const,
    detail: (bookId: number) => ["books", "detail", bookId] as const,
    guide: () => ["books", "document-guide"] as const,
    section: (bookId: number, sectionId: number) =>
      ["books", "section", bookId, sectionId] as const,
  },
  curriculum: {
    all: ["curriculum"] as const,
    versions: () => ["curriculum", "versions"] as const,
    approved: () => ["curriculum", "approved"] as const,
    version: (versionId: number) => ["curriculum", "version", versionId] as const,
    subtopic: (subtopicId: number) => ["curriculum", "subtopic", subtopicId] as const,
    guide: () => ["curriculum", "document-guide"] as const,
  },
  questionSets: {
    all: ["question-sets"] as const,
    list: () => ["question-sets", "list"] as const,
    detail: (setVersionId: number) => ["question-sets", "detail", setVersionId] as const,
  },
  instructions: {
    all: ["instructions"] as const,
    list: () => ["instructions", "list"] as const,
  },
  coverage: {
    all: ["coverage"] as const,
    report: (setVersionId?: number) => ["coverage", setVersionId ?? null] as const,
  },
  students: {
    all: ["students"] as const,
    list: () => ["students", "list"] as const,
    detail: (studentId: number) => ["students", "detail", studentId] as const,
    progress: (studentId: number) => ["students", "progress", studentId] as const,
  },
  trainingSessions: {
    all: ["training-sessions"] as const,
    detail: (trainingSessionId: number) =>
      ["training-sessions", "detail", trainingSessionId] as const,
    next: (trainingSessionId: number) => ["training-sessions", "next", trainingSessionId] as const,
  },
  evaluation: {
    all: ["evaluation"] as const,
    batchRuns: () => ["evaluation", "batch-runs"] as const,
    batchRun: (id: string) => ["evaluation", "batch-runs", id] as const,
  },
  auth: {
    me: () => ["auth", "me"] as const,
  },
} as const;

// --- Auth ---------------------------------------------------------------------

/**
 * Logs in against fastapi-users' cookie router, which expects
 * `application/x-www-form-urlencoded` (the OAuth2 password-flow shape) rather
 * than JSON -- the one request in this app the typed `api` client (`client.ts`)
 * can't produce, so it's a plain `fetch` instead.
 */
async function login(email: string, password: string): Promise<void> {
  const response = await fetch("/api/auth/login", {
    method: "POST",
    headers: { "Content-Type": "application/x-www-form-urlencoded" },
    body: new URLSearchParams({ username: email, password }),
  });
  if (!response.ok) {
    throw new ApiError(response.status, "invalid_credentials", "Incorrect email or password.");
  }
}

async function activateCurriculumVersion(
  versionId: number,
): Promise<Schemas["CurriculumVersionDetail"]> {
  const response = await fetch(`${API_BASE_URL}/api/curriculum/versions/${versionId}/activate`, {
    method: "POST",
    headers: { Accept: "application/json" },
  });
  if (!response.ok) {
    let payload: unknown = null;
    try {
      payload = await response.json();
    } catch {
      payload = null;
    }
    const error = (
      payload as { error?: { code?: string; message?: string; detail?: string } } | null
    )?.error;
    throw new ApiError(
      response.status,
      error?.code ?? "request_failed",
      error?.message ?? "Could not activate the curriculum version.",
      error?.detail,
    );
  }
  return (await response.json()) as Schemas["CurriculumVersionDetail"];
}

export function useLogin() {
  const client = useQueryClient();
  return useMutation({
    mutationFn: ({ email, password }: { email: string; password: string }) =>
      login(email, password),
    onSuccess: () => client.invalidateQueries({ queryKey: qk.auth.me() }),
  });
}

/** 401 is the expected signal for "not logged in", not a transient failure. */
export const useCurrentUser = () =>
  useQuery({
    queryKey: qk.auth.me(),
    queryFn: () => unwrap(api.GET("/api/auth/me")),
    retry: false,
  });

export function useLogout() {
  const client = useQueryClient();
  return useMutation({
    mutationFn: () => unwrap(api.POST("/api/auth/logout")),
    onSuccess: () => client.invalidateQueries({ queryKey: qk.auth.me() }),
  });
}

// --- System -----------------------------------------------------------------

export const healthQuery = () =>
  queryOptions({
    queryKey: qk.system.health(),
    queryFn: () => unwrap(api.GET("/api/health")),
    refetchInterval: 30_000,
  });

export const countsQuery = () =>
  queryOptions({
    queryKey: qk.system.counts(),
    queryFn: () => unwrap(api.GET("/api/counts")),
  });

export const configQuery = () =>
  queryOptions({
    queryKey: qk.system.config(),
    queryFn: () => unwrap(api.GET("/api/config")),
    // Provider and schema versions only change when the process restarts.
    staleTime: Number.POSITIVE_INFINITY,
  });

export const useHealth = () => useQuery(healthQuery());
export const useCounts = () => useQuery(countsQuery());
export const useConfig = () => useQuery(configQuery());

// --- Questions --------------------------------------------------------------

type QuestionListParams = {
  limit?: number;
  status?: QuestionStatus;
  curriculum_version_id?: number;
};

export const questionsQuery = (params: QuestionListParams) =>
  queryOptions({
    queryKey: qk.questions.list(params),
    queryFn: () => unwrap(api.GET("/api/questions", { params: { query: params } })),
  });

export const useQuestions = (params: QuestionListParams) => useQuery(questionsQuery(params));

export const useQuestion = (id: number | null, { enabled = true } = {}) =>
  useQuery({
    queryKey: qk.questions.detail(id ?? 0),
    enabled: enabled && id !== null,
    queryFn: () =>
      unwrap(
        api.GET("/api/questions/{question_id}", {
          params: { path: { question_id: id as number } },
        }),
      ),
  });

export const useReviewQueue = (params: { mode: "all" | "scoreable"; after?: number | null }) =>
  useQuery({
    queryKey: qk.questions.reviewQueue(params),
    queryFn: () =>
      unwrap(
        api.GET("/api/questions/review-queue", {
          params: {
            query: {
              mode: params.mode,
              ...(params.after ? { after: params.after } : {}),
            },
          },
        }),
      ),
  });

/**
 * Submit a professor review.
 *
 * A landed review is routed to its calibration cell and may relearn both the
 * generator's type instruction and the judges it named (ADR-037 to ADR-039), so the
 * question list, the queue and the calibration reads are all invalidated — not just
 * the question that was reviewed.
 */
export function useSubmitReview() {
  const client = useQueryClient();
  return useMutation({
    mutationFn: ({ questionId, body }: { questionId: number; body: Schemas["ReviewRequest"] }) =>
      unwrap(
        api.POST("/api/questions/{question_id}/review", {
          params: { path: { question_id: questionId } },
          body,
        }),
      ),
    onSuccess: () => {
      client.invalidateQueries({ queryKey: qk.questions.all });
      client.invalidateQueries({ queryKey: ["calibration"] });
      client.invalidateQueries({ queryKey: ["instructions"] });
    },
  });
}

// --- Generating from book chunks --------------------------------------------

/**
 * Every candidate chunk in one book, with what it has already produced.
 *
 * The plan endpoint is per-book, so a screen that spans several books asks for
 * one plan each and merges them; see `useGenerationPlans`.
 */
export const generationPlanQuery = (bookId: number) =>
  queryOptions({
    queryKey: qk.questions.generationPlan(bookId),
    queryFn: () =>
      unwrap(api.GET("/api/questions/generation-plan", { params: { query: { book_id: bookId } } })),
  });

/** The plans for several books at once, as one loading state. */
export function useGenerationPlans(bookIds: readonly number[]) {
  return useQueries({
    queries: bookIds.map((bookId) => generationPlanQuery(bookId)),
    combine: (results) => ({
      plans: results.flatMap((result) => (result.data ? [result.data] : [])),
      isPending: results.some((result) => result.isPending),
      isError: results.some((result) => result.isError),
      error: results.find((result) => result.error)?.error ?? null,
    }),
  });
}

/** One chunk's full text and its citation, fetched only when it is being read. */
export const useSection = (
  bookId: number | null,
  sectionId: number | null,
  { enabled = true } = {},
) =>
  useQuery({
    queryKey: qk.books.section(bookId ?? 0, sectionId ?? 0),
    enabled: enabled && bookId !== null && sectionId !== null,
    queryFn: () =>
      unwrap(
        api.GET("/api/books/{book_id}/sections/{section_id}", {
          params: { path: { book_id: bookId as number, section_id: sectionId as number } },
        }),
      ),
  });

/**
 * Price a per-chunk spec sheet without generating anything.
 *
 * A POST that reads: the sheet is too large for a query string, and the compiler
 * that decides how many questions each chunk produces — and which format each one
 * gets — belongs to the API, not to this client (ADR-044). Previous totals are
 * kept while a revised sheet is being priced so the footer does not flicker
 * between every keystroke.
 */
export const useBatchPlan = (chunks: readonly ChunkGenerationSpec[]) =>
  useQuery({
    queryKey: qk.questions.batchPlan(chunks),
    enabled: chunks.length > 0,
    placeholderData: keepPreviousData,
    // A plan is a pure function of the sheet, so a cached one never goes stale.
    staleTime: Number.POSITIVE_INFINITY,
    retry: false,
    queryFn: () => unwrap(api.POST("/api/questions/batch-plan", { body: { chunks: [...chunks] } })),
  });

/**
 * Run a per-chunk spec sheet.
 *
 * Synchronous on the server: every question costs one generation call plus one
 * judge call per metric, made in sequence. Each question commits on its own, so a
 * failure part-way through still leaves the questions already paid for — which is
 * why the caller shows what was created rather than treating the run as atomic.
 */
export function useGenerateBatch() {
  const client = useQueryClient();
  return useMutation({
    mutationFn: (body: Schemas["GenerateBatchRequest"]) =>
      unwrap(api.POST("/api/questions/generate-batch", { body })),
    onSuccess: () => {
      client.invalidateQueries({ queryKey: qk.questions.all });
      client.invalidateQueries({ queryKey: qk.system.counts() });
    },
  });
}

// --- Coverage / books / curriculum / students -------------------------------

export const useCoverage = (setVersionId?: number) =>
  useQuery({
    queryKey: qk.coverage.report(setVersionId),
    queryFn: () =>
      unwrap(
        api.GET("/api/coverage", {
          params: { query: setVersionId ? { set_version_id: setVersionId } : {} },
        }),
      ),
  });

// --- Books ------------------------------------------------------------------

export const useBooks = () =>
  useQuery({ queryKey: qk.books.list(), queryFn: () => unwrap(api.GET("/api/books")) });

/** One book with its chapter/section tree and what deleting it would strand. */
export const useBook = (bookId: number) =>
  useQuery({
    queryKey: qk.books.detail(bookId),
    queryFn: () =>
      unwrap(api.GET("/api/books/{book_id}", { params: { path: { book_id: bookId } } })),
  });

/**
 * What a valid book document is, and the prompt that produces one.
 *
 * Rendered by the backend from the ingestion contract, so this client never
 * describes a document the validator would refuse. It only changes when the
 * contract does, hence no refetching.
 */
export const useBookDocumentGuide = () =>
  useQuery({
    queryKey: qk.books.guide(),
    queryFn: () => unwrap(api.GET("/api/books/document-guide")),
    staleTime: Number.POSITIVE_INFINITY,
  });

/**
 * Import a book document.
 *
 * `file` is typed as `string` by the generated types because OpenAPI describes an
 * upload as a binary string; a `File` is what the multipart body actually needs.
 * The cast is confined to this one call rather than leaking into the screens.
 */
export function useImportBook() {
  const client = useQueryClient();
  return useMutation({
    mutationFn: ({ file, title }: { file: File; title?: string }) =>
      unwrap(
        api.POST("/api/books", {
          // An empty title is what the endpoint takes to mean "use the title the
          // document declares", so an omitted override is sent as one.
          body: { file: file as unknown as string, title: title ?? "" },
          bodySerializer(body: { file: unknown; title: string }) {
            const form = new FormData();
            form.append("file", body.file as Blob);
            form.append("title", body.title);
            return form;
          },
        }),
      ),
    onSuccess: () => {
      client.invalidateQueries({ queryKey: qk.books.all });
      client.invalidateQueries({ queryKey: qk.system.counts() });
    },
  });
}

/** Edit a book's labels. Structure is declared by its document and is not editable. */
export function useUpdateBook() {
  const client = useQueryClient();
  return useMutation({
    mutationFn: ({ bookId, body }: { bookId: number; body: Schemas["BookMetadataUpdate"] }) =>
      unwrap(api.PATCH("/api/books/{book_id}", { params: { path: { book_id: bookId } }, body })),
    onSuccess: (_data, { bookId }) => {
      client.invalidateQueries({ queryKey: qk.books.all });
      client.invalidateQueries({ queryKey: qk.books.detail(bookId) });
    },
  });
}

/**
 * Delete a book, its structure and its retained document.
 *
 * The backend refuses with 409 while questions cite the book, so `force` is the
 * professor repeating the request with that count in front of them. Questions are
 * invalidated too: `force` leaves their source citation pointing at nothing.
 */
export function useDeleteBook() {
  const client = useQueryClient();
  return useMutation({
    mutationFn: ({ bookId, force = false }: { bookId: number; force?: boolean }) =>
      unwrap(
        api.DELETE("/api/books/{book_id}", {
          params: { path: { book_id: bookId }, query: { force } },
        }),
      ),
    onSuccess: () => {
      client.invalidateQueries({ queryKey: qk.books.all });
      client.invalidateQueries({ queryKey: qk.questions.all });
      client.invalidateQueries({ queryKey: qk.system.counts() });
    },
  });
}

// --- Curriculum -------------------------------------------------------------

export const useCurriculumVersions = () =>
  useQuery({
    queryKey: qk.curriculum.versions(),
    queryFn: () => unwrap(api.GET("/api/curriculum/versions")),
  });

/** One version with its Topic → Subtopic tree, and what deleting it would cost. */
export const useCurriculumVersion = (versionId: number) =>
  useQuery({
    queryKey: qk.curriculum.version(versionId),
    queryFn: () =>
      unwrap(
        api.GET("/api/curriculum/versions/{version_id}", {
          params: { path: { version_id: versionId } },
        }),
      ),
  });

/**
 * The version question generation is grounded in.
 *
 * A 404 here is a state, not a fault: nothing has been uploaded yet. Retrying
 * cannot change that, so the screen renders the absence instead of an error.
 */
export const useApprovedCurriculum = () =>
  useQuery({
    queryKey: qk.curriculum.approved(),
    queryFn: () => unwrap(api.GET("/api/curriculum/approved")),
    retry: false,
  });

export const useCurriculumSubtopic = (subtopicId: number) =>
  useQuery({
    queryKey: qk.curriculum.subtopic(subtopicId),
    queryFn: () =>
      unwrap(
        api.GET("/api/curriculum/subtopics/{subtopic_id}", {
          params: { path: { subtopic_id: subtopicId } },
        }),
      ),
  });

/**
 * What a valid taxonomy document is, and the prompt that produces one.
 *
 * Rendered by the backend from the taxonomy contract, so this client never
 * describes a document the validator would refuse. It only changes when the
 * contract does, hence no refetching.
 */
export const useTaxonomyDocumentGuide = () =>
  useQuery({
    queryKey: qk.curriculum.guide(),
    queryFn: () => unwrap(api.GET("/api/curriculum/document-guide")),
    staleTime: Number.POSITIVE_INFINITY,
  });

/**
 * Import a taxonomy document.
 *
 * `file` is typed as `string` by the generated types because OpenAPI describes an
 * upload as a binary string; a `File` is what the multipart body actually needs.
 *
 * Unlike the book import there is no title override to send: a taxonomy document
 * declares its own `label`, and a wrong label is a wrong document.
 */
export function useImportTaxonomy() {
  const client = useQueryClient();
  return useMutation({
    mutationFn: ({ file }: { file: File }) =>
      unwrap(
        api.POST("/api/curriculum/versions", {
          body: { file: file as unknown as string },
          bodySerializer(body: { file: unknown }) {
            const form = new FormData();
            form.append("file", body.file as Blob);
            return form;
          },
        }),
      ),
    onSuccess: () => {
      // A valid upload is approved immediately (ADR-021), so it supersedes the
      // previous version too — the whole section is stale, not just the list.
      client.invalidateQueries({ queryKey: qk.curriculum.all });
      client.invalidateQueries({ queryKey: qk.system.counts() });
      // Coverage is computed against the approved taxonomy, so its grid changes.
      client.invalidateQueries({ queryKey: qk.coverage.all });
    },
  });
}

/** Rename a version. Its topics and subtopics come from the document. */
export function useUpdateCurriculumVersion() {
  const client = useQueryClient();
  return useMutation({
    mutationFn: ({
      versionId,
      body,
    }: {
      versionId: number;
      body: Schemas["CurriculumVersionLabelUpdate"];
    }) =>
      unwrap(
        api.PATCH("/api/curriculum/versions/{version_id}", {
          params: { path: { version_id: versionId } },
          body,
        }),
      ),
    onSuccess: () => {
      client.invalidateQueries({ queryKey: qk.curriculum.all });
      // The coverage report echoes the curriculum's label.
      client.invalidateQueries({ queryKey: qk.coverage.all });
    },
  });
}

/** Make an already-approved curriculum version the one generation uses now. */
export function useActivateCurriculumVersion() {
  const client = useQueryClient();
  return useMutation({
    mutationFn: (versionId: number) => activateCurriculumVersion(versionId),
    onSuccess: () => {
      client.invalidateQueries({ queryKey: qk.curriculum.all });
      client.invalidateQueries({ queryKey: qk.coverage.all });
    },
  });
}

/**
 * Rename one topic or subtopic.
 *
 * The stable id is not recomputed, so a student's measured weakness stays
 * attached to the skill they were measured on (ADR-021).
 */
export function useRenameCurriculumItem() {
  const client = useQueryClient();
  return useMutation({
    mutationFn: ({
      kind,
      itemId,
      body,
    }: {
      kind: "topic" | "subtopic";
      itemId: number;
      body: Schemas["CurriculumItemLabelUpdate"];
      // Annotated because the two paths answer with different shapes: a renamed
      // topic comes back with its subtopics, a renamed subtopic on its own.
    }): Promise<Schemas["TopicOut"] | Schemas["SubtopicSummary"]> =>
      kind === "topic"
        ? unwrap(
            api.PATCH("/api/curriculum/topics/{topic_id}", {
              params: { path: { topic_id: itemId } },
              body,
            }),
          )
        : unwrap(
            api.PATCH("/api/curriculum/subtopics/{subtopic_id}", {
              params: { path: { subtopic_id: itemId } },
              body,
            }),
          ),
    onSuccess: () => {
      client.invalidateQueries({ queryKey: qk.curriculum.all });
      // Coverage labels its rows with these names; the counts are unchanged.
      client.invalidateQueries({ queryKey: qk.coverage.all });
    },
  });
}

/**
 * Delete a curriculum version.
 *
 * The backend refuses with 409 while things still name it, so `force` is the
 * professor repeating the request with those counts in front of them. Two of
 * those refusals have no override at all, which is why the dialog reads the
 * backend's own message rather than deciding for itself what may be forced.
 */
export function useDeleteCurriculumVersion() {
  const client = useQueryClient();
  return useMutation({
    mutationFn: ({ versionId, force = false }: { versionId: number; force?: boolean }) =>
      unwrap(
        api.DELETE("/api/curriculum/versions/{version_id}", {
          params: { path: { version_id: versionId }, query: { force } },
        }),
      ),
    onSuccess: () => {
      client.invalidateQueries({ queryKey: qk.curriculum.all });
      client.invalidateQueries({ queryKey: qk.system.counts() });
      client.invalidateQueries({ queryKey: qk.coverage.all });
      // Forced, this strands the taxonomy a question was tagged against.
      client.invalidateQueries({ queryKey: qk.questions.all });
    },
  });
}

export const useQuestionSets = () =>
  useQuery({
    queryKey: qk.questionSets.list(),
    queryFn: () => unwrap(api.GET("/api/question-sets")),
  });

export const useQuestionSet = (setVersionId: number, { enabled = true } = {}) =>
  useQuery({
    queryKey: qk.questionSets.detail(setVersionId),
    enabled,
    queryFn: () =>
      unwrap(
        api.GET("/api/question-sets/{set_version_id}", {
          params: { path: { set_version_id: setVersionId } },
        }),
      ),
  });

export const instructionsQuery = () =>
  queryOptions({
    queryKey: qk.instructions.list(),
    queryFn: () => unwrap(api.GET("/api/instructions")) as Promise<TypeInstructionListResponse>,
  });

export const useInstructions = () => useQuery(instructionsQuery());

export function useRefreshInstruction() {
  const client = useQueryClient();
  return useMutation({
    mutationFn: (questionType: QuestionType) =>
      unwrap(
        api.POST("/api/instructions/{question_type}/refresh", {
          params: { path: { question_type: questionType } },
        }),
      ),
    onSuccess: () => {
      client.invalidateQueries({ queryKey: qk.instructions.all });
      client.invalidateQueries({ queryKey: qk.system.counts() });
    },
  });
}

export function useDeleteInstructionRule() {
  const client = useQueryClient();
  return useMutation({
    mutationFn: ({ questionType, ruleIndex }: { questionType: QuestionType; ruleIndex: number }) =>
      unwrap(
        api.DELETE("/api/instructions/{question_type}/rules/{rule_index}", {
          params: { path: { question_type: questionType, rule_index: ruleIndex } },
        }),
      ),
    onSuccess: () => {
      client.invalidateQueries({ queryKey: qk.instructions.all });
      client.invalidateQueries({ queryKey: qk.system.counts() });
    },
  });
}

export const useStudents = () =>
  useQuery({ queryKey: qk.students.list(), queryFn: () => unwrap(api.GET("/api/students")) });

export const useStudentProgress = (studentId: number | null, { enabled = true } = {}) =>
  useQuery({
    queryKey: qk.students.progress(studentId ?? 0),
    enabled: enabled && studentId !== null,
    queryFn: () =>
      unwrap(
        api.GET("/api/students/{student_id}/progress", {
          params: { path: { student_id: studentId as number } },
        }),
      ),
  });

export function useCreateStudent() {
  const client = useQueryClient();
  return useMutation({
    mutationFn: (body: Schemas["CreateStudentRequest"]) =>
      unwrap(api.POST("/api/students", { body })),
    onSuccess: () => {
      client.invalidateQueries({ queryKey: qk.students.all });
      client.invalidateQueries({ queryKey: qk.system.counts() });
    },
  });
}

export function useStartTrainingSession() {
  const client = useQueryClient();
  return useMutation({
    mutationFn: (body: Schemas["StartTrainingSessionRequest"]) =>
      unwrap(api.POST("/api/training-sessions", { body })),
    onSuccess: (_data, variables) => {
      client.invalidateQueries({ queryKey: qk.students.all });
      client.invalidateQueries({ queryKey: qk.students.progress(variables.student_id) });
    },
  });
}

export const useTrainingSession = (trainingSessionId: number | null, { enabled = true } = {}) =>
  useQuery({
    queryKey: qk.trainingSessions.detail(trainingSessionId ?? 0),
    enabled: enabled && trainingSessionId !== null,
    queryFn: () =>
      unwrap(
        api.GET("/api/training-sessions/{training_session_id}", {
          params: { path: { training_session_id: trainingSessionId as number } },
        }),
      ),
  });

export const useNextQuestion = (trainingSessionId: number | null, { enabled = true } = {}) =>
  useQuery({
    queryKey: qk.trainingSessions.next(trainingSessionId ?? 0),
    enabled: enabled && trainingSessionId !== null,
    retry: false,
    refetchOnWindowFocus: false,
    queryFn: () =>
      unwrap(
        api.GET("/api/training-sessions/{training_session_id}/next", {
          params: { path: { training_session_id: trainingSessionId as number } },
        }),
      ),
  });

export function useAnswerAttempt() {
  const client = useQueryClient();
  return useMutation({
    mutationFn: ({ attemptId, body }: { attemptId: number; body: Schemas["AnswerRequest"] }) =>
      unwrap(
        api.POST("/api/attempts/{attempt_id}/answer", {
          params: { path: { attempt_id: attemptId } },
          body,
        }),
      ),
    onSuccess: (result) => {
      client.invalidateQueries({
        queryKey: qk.trainingSessions.detail(result.training_session_id),
      });
      client.invalidateQueries({
        queryKey: qk.trainingSessions.next(result.training_session_id),
      });
      client.invalidateQueries({ queryKey: qk.students.all });
    },
  });
}

export function useEndTrainingSession() {
  const client = useQueryClient();
  return useMutation({
    mutationFn: (trainingSessionId: number) =>
      unwrap(
        api.POST("/api/training-sessions/{training_session_id}/end", {
          params: { path: { training_session_id: trainingSessionId } },
        }),
      ),
    onSuccess: (result) => {
      client.invalidateQueries({ queryKey: qk.trainingSessions.detail(result.id) });
      client.invalidateQueries({ queryKey: qk.trainingSessions.next(result.id) });
      client.invalidateQueries({ queryKey: qk.students.progress(result.student_id) });
      client.invalidateQueries({ queryKey: qk.students.all });
    },
  });
}

// --- Judge batch runs -------------------------------------------------------

/**
 * Watch a judge batch run.
 *
 * Batch jobs are submitted now and collected later (ADR-030), so the client polls.
 * Polling stops as soon as the run leaves a running state rather than continuing
 * forever in a background tab.
 */
export function useBatchRun(runId: string, { enabled = true } = {}) {
  return useQuery({
    queryKey: qk.evaluation.batchRun(runId),
    enabled,
    queryFn: () =>
      unwrap(
        api.GET("/api/evaluation/batch-runs/{run_id}", { params: { path: { run_id: runId } } }),
      ),
    refetchInterval: (query) => {
      const status = query.state.data?.status;
      // A provider-side cancellation is recorded as `failed`, so these three are
      // the whole terminal set.
      return status === "completed" || status === "failed" || status === "expired" ? false : 5_000;
    },
  });
}
