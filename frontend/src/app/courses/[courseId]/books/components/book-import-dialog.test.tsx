import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { useState } from "react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { BookImportDialog } from "./book-import-dialog";

const mutateAsync = vi.fn();
const { setJobParam } = vi.hoisted(() => ({ setJobParam: vi.fn() }));

vi.mock("nuqs", () => ({
  parseAsString: {},
  useQueryState: () => [null, setJobParam],
}));
vi.mock("@/lib/api/queries", () => ({
  useConfig: () => ({
    data: { supported_book_extensions: [".docx", ".pdf", ".pptx"], max_book_upload_mb: 5 },
  }),
  useImportBook: () => ({ mutateAsync, reset: vi.fn(), isPending: false, error: null }),
}));

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
  mutateAsync.mockReset();
  setJobParam.mockReset();
});

describe("BookImportDialog", () => {
  it("offers the file types the backend reads, and the title only under Advanced options", async () => {
    const user = userEvent.setup();
    render(<Harness />);

    expect(screen.getByLabelText("Book file")).toHaveAttribute("accept", ".docx,.pdf,.pptx");
    expect(screen.queryByLabelText("Title")).not.toBeInTheDocument();

    await user.click(screen.getByRole("button", { name: "Advanced options" }));
    expect(screen.getByLabelText("Title")).toBeInTheDocument();
  });

  it("starts the import with its title override, closes, and opens the job", async () => {
    mutateAsync.mockResolvedValue({ job_id: "job-7" });
    const user = userEvent.setup();
    render(<Harness />);

    const file = new File(["%PDF-1.4"], "book.pdf", { type: "application/pdf" });
    await user.upload(screen.getByLabelText("Book file"), file);
    await user.click(screen.getByRole("button", { name: "Advanced options" }));
    await user.type(screen.getByLabelText("Title"), "Custom");
    await user.click(screen.getByRole("button", { name: "Import book" }));

    await waitFor(() => expect(mutateAsync).toHaveBeenCalledWith({ file, title: "Custom" }));
    await waitFor(() => expect(screen.getByText("closed")).toBeInTheDocument());
    expect(setJobParam).toHaveBeenCalledWith("job-7");
  });

  it("stays open when the file is refused", async () => {
    mutateAsync.mockRejectedValue(new Error("refused"));
    const user = userEvent.setup();
    render(<Harness />);

    const file = new File(["%PDF-1.4"], "book.pdf", { type: "application/pdf" });
    await user.upload(screen.getByLabelText("Book file"), file);
    await user.click(screen.getByRole("button", { name: "Import book" }));

    await waitFor(() => expect(mutateAsync).toHaveBeenCalled());
    expect(screen.getByText("open")).toBeInTheDocument();
    expect(setJobParam).not.toHaveBeenCalled();
  });

  it("says what is missing when nothing was chosen, and sends nothing", async () => {
    const user = userEvent.setup();
    render(<Harness />);

    await user.click(screen.getByRole("button", { name: "Import book" }));

    expect(await screen.findByText("Choose a book file.")).toBeInTheDocument();
    expect(mutateAsync).not.toHaveBeenCalled();
  });
});
