import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { useState } from "react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { ApiError } from "@/lib/api/client";
import { BookImportDialog } from "./book-import-dialog";

const importFile = vi.fn();
const importVideo = vi.fn();
let videoError: unknown = null;
const { setJobParam } = vi.hoisted(() => ({ setJobParam: vi.fn() }));

vi.mock("sonner", () => ({ toast: { success: vi.fn() } }));
vi.mock("nuqs", () => ({
  parseAsString: {},
  useQueryState: () => [null, setJobParam],
}));
vi.mock("@/lib/api/queries", () => ({
  useConfig: () => ({
    data: { supported_book_extensions: [".docx", ".pdf", ".pptx"], max_book_upload_mb: 5 },
  }),
  useImportBook: () => ({ mutateAsync: importFile, reset: vi.fn(), isPending: false, error: null }),
  useImportYoutube: () => ({
    mutateAsync: async (body: unknown) => {
      try {
        return await importVideo(body);
      } catch (caught) {
        videoError = caught;
        throw caught;
      }
    },
    reset: () => {
      videoError = null;
    },
    isPending: false,
    get error() {
      return videoError;
    },
  }),
}));

const PDF = () => new File(["%PDF-1.4"], "book.pdf", { type: "application/pdf" });
const YOUTUBE = "https://youtu.be/AbCdEfGhIjK";

function Harness() {
  const [open, setOpen] = useState(true);
  return (
    <>
      <span>{open ? "open" : "closed"}</span>
      <BookImportDialog open={open} onOpenChange={setOpen} />
    </>
  );
}

beforeEach(() => {
  importFile.mockReset();
  importVideo.mockReset();
  setJobParam.mockReset();
  videoError = null;
});

describe("BookImportDialog", () => {
  it("offers the file types the backend reads, and the title only under Advanced options", async () => {
    const user = userEvent.setup();
    render(<Harness />);

    expect(screen.getByLabelText("Choose a file")).toHaveAttribute("accept", ".docx,.pdf,.pptx");
    expect(screen.getByText("Word, PDF, PowerPoint, up to 5 MB")).toBeInTheDocument();
    expect(screen.queryByLabelText("Title")).not.toBeInTheDocument();

    await user.click(screen.getByRole("button", { name: "Advanced options" }));
    expect(screen.getByLabelText("Title")).toBeInTheDocument();
  });

  it("starts a file's import with its title override, closes, and opens the job", async () => {
    importFile.mockResolvedValue({ job_id: "job-7" });
    const user = userEvent.setup();
    render(<Harness />);

    const file = PDF();
    await user.upload(screen.getByLabelText("Choose a file"), file);
    expect(screen.getByText("book.pdf")).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Advanced options" }));
    await user.type(screen.getByLabelText("Title"), "Custom");
    await user.click(screen.getByRole("button", { name: "Upload file" }));

    await waitFor(() => expect(importFile).toHaveBeenCalledWith({ file, title: "Custom" }));
    await waitFor(() => expect(screen.getByText("closed")).toBeInTheDocument());
    expect(setJobParam).toHaveBeenCalledWith("job-7");
  });

  it("takes a dropped file", async () => {
    render(<Harness />);
    const file = PDF();
    fireEvent.drop(screen.getByRole("region", { name: "Drop a file" }), {
      dataTransfer: { files: [file], getData: () => "" },
    });
    expect(await screen.findByText("book.pdf")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Upload file" })).toBeEnabled();
  });

  it("takes a pasted file, and a pasted link outside a text box", async () => {
    render(<Harness />);
    const zone = screen.getByRole("region", { name: "Drop a file" });

    fireEvent.paste(zone, { clipboardData: { files: [PDF()], getData: () => "" } });
    expect(await screen.findByText("book.pdf")).toBeInTheDocument();

    fireEvent.paste(zone, { clipboardData: { files: [], getData: () => YOUTUBE } });
    expect(screen.getByLabelText("Paste a link")).toHaveValue(YOUTUBE);
    expect(screen.queryByText("book.pdf")).not.toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Import video" })).toBeInTheDocument();
  });

  it("refuses a file type it cannot read before sending it", async () => {
    render(<Harness />);
    fireEvent.drop(screen.getByRole("region", { name: "Drop a file" }), {
      dataTransfer: { files: [new File(["x"], "clip.mp4")], getData: () => "" },
    });
    await userEvent.setup().click(await screen.findByRole("button", { name: "Upload file" }));

    expect(await screen.findByText(/This file type cannot be read/)).toBeInTheDocument();
    expect(importFile).not.toHaveBeenCalled();
  });

  it("stays open when the file is refused", async () => {
    importFile.mockRejectedValue(new Error("refused"));
    const user = userEvent.setup();
    render(<Harness />);

    await user.upload(screen.getByLabelText("Choose a file"), PDF());
    await user.click(screen.getByRole("button", { name: "Upload file" }));

    await waitFor(() => expect(importFile).toHaveBeenCalled());
    expect(screen.getByText("open")).toBeInTheDocument();
    expect(setJobParam).not.toHaveBeenCalled();
  });

  it("says what is missing when nothing was chosen, and sends nothing", async () => {
    const user = userEvent.setup();
    render(<Harness />);

    await user.click(screen.getByRole("button", { name: "Upload" }));

    expect(await screen.findByText("Choose a file or paste a link.")).toBeInTheDocument();
    expect(importFile).not.toHaveBeenCalled();
    expect(importVideo).not.toHaveBeenCalled();
  });

  it("imports a YouTube link and closes", async () => {
    importVideo.mockResolvedValue({ book: { id: 3, title: "Loops in Python" } });
    const user = userEvent.setup();
    render(<Harness />);

    await user.type(screen.getByLabelText("Paste a link"), YOUTUBE);
    await user.click(screen.getByRole("button", { name: "Import video" }));

    await waitFor(() => expect(screen.getByText("closed")).toBeInTheDocument());
    expect(importVideo).toHaveBeenCalledWith({ url: YOUTUBE, title: "", transcript: "" });
  });

  it("asks for the transcript when YouTube will not give it, then sends it with the link", async () => {
    importVideo
      .mockRejectedValueOnce(
        new ApiError(422, "transcript_unavailable", "YouTube did not give us this transcript."),
      )
      .mockResolvedValueOnce({ book: { id: 3, title: "Loops in Python" } });
    const user = userEvent.setup();
    render(<Harness />);

    await user.type(screen.getByLabelText("Paste a link"), YOUTUBE);
    await user.click(screen.getByRole("button", { name: "Import video" }));
    await user.type(await screen.findByLabelText("Transcript"), "0:00 Welcome back.");
    await user.click(screen.getByRole("button", { name: "Import with transcript" }));

    await waitFor(() => expect(screen.getByText("closed")).toBeInTheDocument());
    expect(importVideo).toHaveBeenLastCalledWith({
      url: YOUTUBE,
      title: "",
      transcript: "0:00 Welcome back.",
    });
  });

  it("explains a video link it cannot import and sends nothing", async () => {
    const user = userEvent.setup();
    render(<Harness />);

    await user.type(screen.getByLabelText("Paste a link"), "https://vimeo.com/123456");

    expect(screen.getByText(/Only YouTube videos can be imported for now/)).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Upload" })).toBeDisabled();
    expect(importVideo).not.toHaveBeenCalled();
  });
});
