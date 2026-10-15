import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { ApiError } from "@/lib/api/client";
import { YoutubeImportForm } from "./youtube-import-form";

const mutateAsync = vi.fn();
let error: unknown = null;

vi.mock("sonner", () => ({ toast: { success: vi.fn() } }));
vi.mock("@/lib/api/queries", () => ({
  useImportYoutube: () => ({
    mutateAsync: async (body: unknown) => {
      try {
        return await mutateAsync(body);
      } catch (caught) {
        error = caught;
        throw caught;
      }
    },
    reset: () => {
      error = null;
    },
    isPending: false,
    get error() {
      return error;
    },
  }),
}));

const URL = "https://youtu.be/AbCdEfGhIjK";
const BOOK = { book: { id: 3, title: "Loops in Python" } };

beforeEach(() => {
  mutateAsync.mockReset();
  error = null;
});

describe("YoutubeImportForm", () => {
  it("imports from the link alone and closes", async () => {
    mutateAsync.mockResolvedValue(BOOK);
    const onImported = vi.fn();
    const user = userEvent.setup();
    render(<YoutubeImportForm onImported={onImported} />);

    await user.type(screen.getByLabelText("YouTube link"), URL);
    await user.click(screen.getByRole("button", { name: "Import video" }));

    await waitFor(() => expect(onImported).toHaveBeenCalled());
    expect(mutateAsync).toHaveBeenCalledWith({ url: URL, title: "", transcript: "" });
    expect(screen.queryByLabelText("Transcript")).not.toBeInTheDocument();
  });

  it("offers the paste when the fetch fails, then sends the transcript with the link", async () => {
    mutateAsync
      .mockRejectedValueOnce(
        new ApiError(422, "transcript_unavailable", "YouTube did not give us this transcript."),
      )
      .mockResolvedValueOnce(BOOK);
    const onImported = vi.fn();
    const user = userEvent.setup();
    const { rerender } = render(<YoutubeImportForm onImported={onImported} />);

    await user.type(screen.getByLabelText("YouTube link"), URL);
    await user.click(screen.getByRole("button", { name: "Import video" }));

    const paste = await screen.findByLabelText("Transcript");
    rerender(<YoutubeImportForm onImported={onImported} />);
    expect(onImported).not.toHaveBeenCalled();
    await user.type(paste, "0:00 Welcome back.");
    await user.click(screen.getByRole("button", { name: "Import with transcript" }));

    await waitFor(() => expect(onImported).toHaveBeenCalled());
    expect(mutateAsync).toHaveBeenLastCalledWith({
      url: URL,
      title: "",
      transcript: "0:00 Welcome back.",
    });
  });

  it("shows any other refusal with the backend's wording and stays open", async () => {
    mutateAsync.mockRejectedValue(
      new ApiError(
        422,
        "domain_rule_violation",
        "This video is private, deleted or does not exist.",
      ),
    );
    const onImported = vi.fn();
    const user = userEvent.setup();
    const { rerender } = render(<YoutubeImportForm onImported={onImported} />);

    await user.type(screen.getByLabelText("YouTube link"), URL);
    await user.click(screen.getByRole("button", { name: "Import video" }));
    await waitFor(() => expect(mutateAsync).toHaveBeenCalled());
    rerender(<YoutubeImportForm onImported={onImported} />);

    expect(await screen.findByText(/private, deleted/)).toBeInTheDocument();
    expect(screen.queryByLabelText("Transcript")).not.toBeInTheDocument();
    expect(onImported).not.toHaveBeenCalled();
  });
});
