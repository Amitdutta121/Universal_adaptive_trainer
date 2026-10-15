import { beforeEach, describe, expect, it, vi } from "vitest";

const GET = vi.fn();

vi.mock("./client", async (importOriginal) => {
  const actual = await importOriginal<typeof import("./client")>();
  return {
    ...actual,
    api: { ...actual.api, GET: (...args: unknown[]) => GET(...args) },
    unwrap: async (call: Promise<{ data: unknown }>) => (await call).data,
  };
});

const { waitForJob } = await import("./queries");

function listing(...jobs: { id: string; status: string; error?: string | null }[]) {
  return Promise.resolve({ data: { jobs } });
}

describe("waitForJob", () => {
  beforeEach(() => GET.mockReset());

  it("polls until the job is done and returns it", async () => {
    GET.mockReturnValueOnce(listing({ id: "job-1", status: "queued" }))
      .mockReturnValueOnce(listing({ id: "job-1", status: "running" }))
      .mockReturnValueOnce(
        listing({ id: "job-2", status: "done" }, { id: "job-1", status: "done" }),
      );

    const job = await waitForJob("job-1", 0);

    expect(job.id).toBe("job-1");
    expect(GET).toHaveBeenCalledTimes(3);
  });

  it("keeps polling while the job is not listed yet", async () => {
    GET.mockReturnValueOnce(listing()).mockReturnValueOnce(
      listing({ id: "job-1", status: "done" }),
    );

    await expect(waitForJob("job-1", 0)).resolves.toMatchObject({ status: "done" });
  });

  it("throws the job's own error when it fails", async () => {
    GET.mockReturnValueOnce(
      listing({ id: "job-1", status: "failed", error: "The model provider is unavailable." }),
    );

    await expect(waitForJob("job-1", 0)).rejects.toThrow("The model provider is unavailable.");
  });

  it("throws when the job is cancelled", async () => {
    GET.mockReturnValueOnce(listing({ id: "job-1", status: "cancelled", error: null }));

    await expect(waitForJob("job-1", 0)).rejects.toThrow("stopped before it finished");
  });
});
