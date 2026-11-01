import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { NuqsTestingAdapter } from "nuqs/adapters/testing";
import { beforeAll, beforeEach, describe, expect, it, vi } from "vitest";
import type { Job } from "@/lib/api/types";

vi.mock("next/navigation", async (importOriginal) => ({
  ...(await importOriginal<typeof import("next/navigation")>()),
  useParams: () => ({ courseId: "7" }),
}));

const toast = vi.hoisted(() => ({ success: vi.fn(), error: vi.fn() }));
vi.mock("sonner", () => ({ toast }));

const invalidateQueries = vi.fn();
vi.mock("@tanstack/react-query", async (importOriginal) => ({
  ...(await importOriginal<typeof import("@tanstack/react-query")>()),
  useQueryClient: () => ({ invalidateQueries }),
}));

let jobs: Job[] = [];
vi.mock("@/lib/api/queries", async (importOriginal) => ({
  ...(await importOriginal<typeof import("@/lib/api/queries")>()),
  useJobs: () => ({ isPending: false, isError: false, data: { jobs } }),
  useCancelJob: () => ({ mutateAsync: vi.fn(), isPending: false }),
  useRetryJob: () => ({ mutateAsync: vi.fn(), isPending: false }),
}));

import { JobDetailDialog } from "./job-detail-dialog";
import { JobsMenu } from "./jobs-menu";

function job(overrides: Partial<Job>): Job {
  return {
    id: "job-1",
    kind: "bulk_generation",
    title: "Bulk generate · 40 questions",
    status: "running",
    done: 18,
    total: 40,
    counts: {},
    error: null,
    link: "/questions?run_id=abc",
    result: null,
    can_cancel: false,
    cancel_requested: false,
    retry_label: null,
    created_at: "2026-10-06T12:00:00",
    started_at: "2026-10-06T12:00:01",
    finished_at: null,
    ...overrides,
  };
}

const running = job({});
const round = job({
  id: "round-5",
  kind: "question_round",
  title: "Question round 1 · Intro Python",
  status: "queued",
  done: 0,
  total: 10,
  counts: { made: 0, dropped: 0, skipped: 0 },
  link: "/review?round=5",
});
const failed = job({
  id: "job-2",
  title: "Bulk generate · 25 questions",
  status: "failed",
  done: 11,
  total: 25,
  error: "LLM rate limit (429) after 3 retries",
  finished_at: "2026-10-06T11:15:44",
});
const judged = job({
  id: "judge-r1",
  kind: "judge_run",
  title: "Judge run · 60 questions",
  status: "done",
  done: 60,
  total: 60,
  counts: { judged: 51, failed: 9 },
  link: "/judges",
  finished_at: "2026-10-05T10:00:00",
});

beforeAll(() => {
  globalThis.ResizeObserver ??= class {
    observe() {}
    unobserve() {}
    disconnect() {}
  } as unknown as typeof ResizeObserver;
});

beforeEach(() => {
  toast.success.mockClear();
  toast.error.mockClear();
  invalidateQueries.mockClear();
});

function renderMenu() {
  return render(
    <NuqsTestingAdapter>
      <JobsMenu />
    </NuqsTestingAdapter>,
  );
}

describe("JobsMenu", () => {
  it("counts running jobs on the button and lists in-progress then finished jobs", async () => {
    jobs = [running, round, failed, judged];
    renderMenu();

    const button = screen.getByRole("button", { name: /Jobs/ });
    expect(within(button).getByText("1")).toBeInTheDocument();

    await userEvent.click(button);

    expect(screen.getByText("1 running · 1 queued")).toBeInTheDocument();
    expect(screen.getByText("In progress")).toBeInTheDocument();
    expect(screen.getByText("Recently finished")).toBeInTheDocument();
    expect(screen.getByText("Waiting to start")).toBeInTheDocument();
    expect(screen.getByText(/LLM rate limit \(429\)/)).toBeInTheDocument();
    expect(screen.getByText(/51 questions judged · 9 failed/)).toBeInTheDocument();
  });

  it("says so when nothing has run yet", async () => {
    jobs = [];
    renderMenu();

    await userEvent.click(screen.getByRole("button", { name: /Jobs/ }));

    expect(screen.getByText(/Nothing has run in this course yet/)).toBeInTheDocument();
  });

  it("opens the run window on the first running job from View all", async () => {
    jobs = [failed, running];
    renderMenu();

    await userEvent.click(screen.getByRole("button", { name: /Jobs/ }));
    await userEvent.click(screen.getByRole("button", { name: "View all jobs →" }));

    const dialog = await screen.findByRole("dialog");
    expect(within(dialog).getByRole("heading", { name: running.title })).toBeInTheDocument();
    expect(within(dialog).getByText("18 / 40")).toBeInTheDocument();
  });

  it("announces a job that finishes and refreshes what it changed", () => {
    jobs = [running];
    const { rerender } = renderMenu();
    expect(toast.success).not.toHaveBeenCalled();

    jobs = [{ ...running, status: "done", done: 40, finished_at: "2026-10-06T12:06:00" }];
    rerender(
      <NuqsTestingAdapter>
        <JobsMenu />
      </NuqsTestingAdapter>,
    );

    expect(toast.success).toHaveBeenCalledWith(
      "Bulk generate · 40 questions finished",
      expect.objectContaining({ description: "40 questions" }),
    );
    expect(invalidateQueries).toHaveBeenCalledWith({ queryKey: ["questions"] });
  });

  it("does not announce jobs that had already finished when the page loaded", () => {
    jobs = [failed, judged];
    renderMenu();

    expect(toast.success).not.toHaveBeenCalled();
    expect(toast.error).not.toHaveBeenCalled();
  });
});

describe("JobDetailDialog", () => {
  function renderDialog(jobParam: string, onSelect = vi.fn()) {
    render(
      <NuqsTestingAdapter>
        <JobDetailDialog
          jobs={[running, round, failed, judged]}
          jobParam={jobParam}
          onSelect={onSelect}
          onClose={vi.fn()}
        />
      </NuqsTestingAdapter>,
    );
    return screen.getByRole("dialog");
  }

  it("shows a failed job's error and a link to what it kept", () => {
    const dialog = renderDialog("job-2");

    expect(within(dialog).getByText("LLM rate limit (429) after 3 retries")).toBeInTheDocument();
    expect(within(dialog).getByRole("link", { name: "Open these questions →" })).toHaveAttribute(
      "href",
      "/courses/7/questions?run_id=abc",
    );
  });

  it("shows a round's breakdown and links it to the review queue", () => {
    const dialog = renderDialog("round-5");

    expect(within(dialog).getByText("Made")).toBeInTheDocument();
    expect(within(dialog).getByText("Dropped")).toBeInTheDocument();
    expect(within(dialog).getByRole("link", { name: "Open in review →" })).toHaveAttribute(
      "href",
      "/courses/7/review?round=5",
    );
  });

  it("filters the list by tab and selects a job from it", async () => {
    const onSelect = vi.fn();
    const dialog = renderDialog("job-1", onSelect);

    await userEvent.click(within(dialog).getByRole("tab", { name: /Failed/ }));
    const list = within(dialog).getAllByRole("listitem");
    expect(list).toHaveLength(1);

    await userEvent.click(within(list[0]).getByRole("button"));
    expect(onSelect).toHaveBeenCalledWith("job-2");
  });
});
