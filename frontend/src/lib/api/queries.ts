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

import { queryOptions, useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { api, unwrap } from "./client";
import type { QuestionStatus, Schemas } from "./types";

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
  },
  books: { all: ["books"] as const, list: () => ["books", "list"] as const },
  curriculum: {
    all: ["curriculum"] as const,
    versions: () => ["curriculum", "versions"] as const,
    approved: () => ["curriculum", "approved"] as const,
  },
  coverage: (setVersionId?: number) => ["coverage", setVersionId ?? null] as const,
  students: { all: ["students"] as const, list: () => ["students", "list"] as const },
  evaluation: {
    all: ["evaluation"] as const,
    batchRuns: () => ["evaluation", "batch-runs"] as const,
    batchRun: (id: string) => ["evaluation", "batch-runs", id] as const,
  },
} as const;

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

export const questionsQuery = (params: { limit?: number; status?: QuestionStatus }) =>
  queryOptions({
    queryKey: qk.questions.list(params),
    queryFn: () => unwrap(api.GET("/api/questions", { params: { query: params } })),
  });

export const useQuestions = (params: { limit?: number; status?: QuestionStatus }) =>
  useQuery(questionsQuery(params));

export const useQuestion = (id: number) =>
  useQuery({
    queryKey: qk.questions.detail(id),
    queryFn: () =>
      unwrap(api.GET("/api/questions/{question_id}", { params: { path: { question_id: id } } })),
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

// --- Coverage / books / curriculum / students -------------------------------

export const useCoverage = (setVersionId?: number) =>
  useQuery({
    queryKey: qk.coverage(setVersionId),
    queryFn: () =>
      unwrap(
        api.GET("/api/coverage", {
          params: { query: setVersionId ? { set_version_id: setVersionId } : {} },
        }),
      ),
  });

export const useBooks = () =>
  useQuery({ queryKey: qk.books.list(), queryFn: () => unwrap(api.GET("/api/books")) });

export const useCurriculumVersions = () =>
  useQuery({
    queryKey: qk.curriculum.versions(),
    queryFn: () => unwrap(api.GET("/api/curriculum/versions")),
  });

export const useStudents = () =>
  useQuery({ queryKey: qk.students.list(), queryFn: () => unwrap(api.GET("/api/students")) });

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
