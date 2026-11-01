import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";
import type { Job } from "@/lib/api/types";

vi.mock("sonner", () => ({ toast: { success: vi.fn(), error: vi.fn() } }));

const cancelJob = vi.fn();
const retryJob = vi.fn();
vi.mock("@/lib/api/queries", () => ({
  useCancelJob: () => ({ mutateAsync: cancelJob, isPending: false }),
  useRetryJob: () => ({ mutateAsync: retryJob, isPending: false }),
}));

import { JobActions } from "./job-actions";

function job(overrides: Partial<Job>): Job {
  return {
    id: "job-3",
    kind: "bulk_generation",
    title: "Bulk generate · 25 questions",
    status: "running",
    done: 11,
    total: 25,
    counts: {},
    error: null,
    link: null,
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

beforeEach(() => {
  cancelJob.mockReset().mockResolvedValue({});
  retryJob.mockReset().mockResolvedValue({ job_id: "job-4" });
});

describe("JobActions", () => {
  it("cancels a job the server says can be cancelled", async () => {
    render(<JobActions job={job({ can_cancel: true })} />);

    await userEvent.click(screen.getByRole("button", { name: /Cancel/ }));

    expect(cancelJob).toHaveBeenCalledWith("job-3");
    expect(screen.queryByRole("button", { name: /Retry/ })).not.toBeInTheDocument();
  });

  it("says a job is stopping once a cancel was asked for", () => {
    render(<JobActions job={job({ cancel_requested: true })} />);

    expect(screen.getByText(/Stopping after the current question/)).toBeInTheDocument();
    expect(screen.queryByRole("button")).not.toBeInTheDocument();
  });

  it("retries with the server's label and hands over the new job", async () => {
    const onRetried = vi.fn();
    render(
      <JobActions
        job={job({ status: "cancelled", retry_label: "Retry the remaining 14" })}
        onRetried={onRetried}
      />,
    );

    await userEvent.click(screen.getByRole("button", { name: /Retry the remaining 14/ }));

    expect(retryJob).toHaveBeenCalledWith("job-3");
    expect(onRetried).toHaveBeenCalledWith("job-4");
  });

  it("explains that a running judge run cannot be stopped", () => {
    render(<JobActions job={job({ id: "judge-r1", kind: "judge_run" })} />);

    expect(screen.getByText(/can't be stopped once it is submitted/)).toBeInTheDocument();
    expect(screen.queryByRole("button")).not.toBeInTheDocument();
  });

  it("offers nothing for a finished job with nothing left to do", () => {
    const { container } = render(<JobActions job={job({ status: "done", done: 25 })} />);

    expect(container).toBeEmptyDOMElement();
  });
});
