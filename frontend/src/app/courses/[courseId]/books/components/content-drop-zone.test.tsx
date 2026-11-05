import { act, render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { ApiError } from "@/lib/api/client";
import { ContentDropZone } from "./content-drop-zone";

const importFile = vi.fn();
const importVideo = vi.fn();
const { toast } = vi.hoisted(() => ({
  toast: { loading: vi.fn(() => "t"), success: vi.fn(), error: vi.fn(), dismiss: vi.fn() },
}));

vi.mock("sonner", () => ({ toast }));
vi.mock("@/lib/api/queries", () => ({
  useConfig: () => ({ data: { supported_book_extensions: [".pdf", ".docx"], max_book_upload_mb: 5 } }),
  useImportBook: () => ({ mutateAsync: importFile }),
  useImportYoutube: () => ({ mutateAsync: importVideo }),
}));

/** A native drag event carrying `files` or a dragged link, as the browser sends it. */
function drag(type: string, { files = [] as File[], link = "" } = {}) {
  const event = new Event(type, { bubbles: true, cancelable: true });
  const types = [...(files.length ? ["Files"] : []), ...(link ? ["text/uri-list"] : [])];
  Object.defineProperty(event, "dataTransfer", {
    value: { types, files, getData: (kind: string) => (kind === "text/uri-list" ? link : "") },
  });
  act(() => {
    window.dispatchEvent(event);
  });
  return event;
}

const pdf = (name = "book.pdf") => new File(["%PDF-1.4"], name, { type: "application/pdf" });

beforeEach(() => {
  importFile.mockReset().mockResolvedValue({ job_id: "job-1" });
  importVideo.mockReset();
  for (const fn of Object.values(toast)) fn.mockClear();
});

describe("ContentDropZone", () => {
  it("shows the drop target while a file is dragged over the page", () => {
    render(<ContentDropZone onNeedsTranscript={vi.fn()} />);

    drag("dragenter", { files: [pdf()] });
    expect(screen.getByText("Drop to upload")).toBeInTheDocument();
    drag("dragleave", { files: [pdf()] });
    expect(screen.queryByText("Drop to upload")).not.toBeInTheDocument();
  });

  it("uploads every dropped file and refuses the ones the backend would", async () => {
    render(<ContentDropZone onNeedsTranscript={vi.fn()} />);

    const event = drag("drop", { files: [pdf("a.pdf"), pdf("clip.mp4"), pdf("b.pdf")] });

    expect(event.defaultPrevented).toBe(true);
    await waitFor(() => expect(importFile).toHaveBeenCalledTimes(2));
    expect(importFile.mock.calls.map(([body]) => body.file.name)).toEqual(["a.pdf", "b.pdf"]);
    expect(toast.error).toHaveBeenCalledWith("clip.mp4", expect.anything());
  });

  it("imports a dropped YouTube link and hands a missing transcript to the uploader", async () => {
    const onNeedsTranscript = vi.fn();
    importVideo.mockRejectedValue(
      new ApiError(422, "transcript_unavailable", "No captions"),
    );
    render(<ContentDropZone onNeedsTranscript={onNeedsTranscript} />);

    drag("drop", { link: "https://youtu.be/AbCdEfGhIjK" });

    await waitFor(() => expect(onNeedsTranscript).toHaveBeenCalledWith("https://youtu.be/AbCdEfGhIjK"));
    expect(importVideo).toHaveBeenCalledWith({
      url: "https://youtu.be/AbCdEfGhIjK",
      title: "",
      transcript: "",
    });
  });

  it("leaves a drop to the open uploader dialog", () => {
    render(<ContentDropZone disabled onNeedsTranscript={vi.fn()} />);

    const event = drag("drop", { files: [pdf()] });

    expect(event.defaultPrevented).toBe(true);
    expect(importFile).not.toHaveBeenCalled();
  });
});
