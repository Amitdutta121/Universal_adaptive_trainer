import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { useState } from "react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { BookImportDialog } from "./book-import-dialog";

const mutateAsync = vi.fn();

vi.mock("sonner", () => ({ toast: { success: vi.fn() } }));
// The guide's own card is not what is under test here.
vi.mock("./document-guide-card", () => ({ DocumentGuideCard: () => <div>guide card</div> }));
vi.mock("@/lib/api/queries", () => ({
  useBookDocumentGuide: () => ({
    data: { schema_version: "1", supported_extensions: [".json", ".pdf"], max_upload_mb: 5 },
    isPending: false,
    error: null,
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

const DOCUMENT = '{"schema_version":"1","title":"T","chapters":[]}';

beforeEach(() => {
  mutateAsync.mockReset();
});

describe("BookImportDialog", () => {
  it("shows only the file field until Advanced options is opened", async () => {
    const user = userEvent.setup();
    render(<Harness />);

    expect(screen.getByLabelText("Book file")).toBeInTheDocument();
    expect(screen.queryByLabelText("Title")).not.toBeInTheDocument();
    expect(screen.queryByText("guide card")).not.toBeInTheDocument();

    await user.click(screen.getByRole("button", { name: "Advanced options" }));
    expect(screen.getByLabelText("Title")).toBeInTheDocument();
    expect(screen.getByLabelText("Paste JSON instead of a file")).toBeInTheDocument();
    expect(screen.getByText("guide card")).toBeInTheDocument();
  });

  it("imports a chosen file with its title override and closes on success", async () => {
    mutateAsync.mockResolvedValue({ title: "Custom", status: "imported" });
    const user = userEvent.setup();
    render(<Harness />);

    const file = new File(["%PDF-1.4"], "book.pdf", { type: "application/pdf" });
    await user.upload(screen.getByLabelText("Book file"), file);
    await user.click(screen.getByRole("button", { name: "Advanced options" }));
    await user.type(screen.getByLabelText("Title"), "Custom");
    await user.click(screen.getByRole("button", { name: "Import book" }));

    await waitFor(() => expect(mutateAsync).toHaveBeenCalledWith({ file, title: "Custom" }));
    await waitFor(() => expect(screen.getByText("closed")).toBeInTheDocument());
  });

  it("imports pasted JSON as a document", async () => {
    mutateAsync.mockResolvedValue({ title: "T", status: "imported" });
    const user = userEvent.setup();
    render(<Harness />);

    await user.click(screen.getByRole("button", { name: "Advanced options" }));
    await user.click(screen.getByLabelText("Paste JSON instead of a file"));
    await user.paste(DOCUMENT);
    await user.click(screen.getByRole("button", { name: "Import book" }));

    await waitFor(() => expect(mutateAsync).toHaveBeenCalledTimes(1));
    const [[{ file }]] = mutateAsync.mock.calls as [[{ file: File }]];
    expect(await file.text()).toBe(DOCUMENT);
  });

  it("stays open with the text intact when the document is refused", async () => {
    mutateAsync.mockRejectedValue(new Error("refused"));
    const user = userEvent.setup();
    render(<Harness />);

    await user.click(screen.getByRole("button", { name: "Advanced options" }));
    await user.click(screen.getByLabelText("Paste JSON instead of a file"));
    await user.paste(DOCUMENT);
    await user.click(screen.getByRole("button", { name: "Import book" }));

    await waitFor(() => expect(mutateAsync).toHaveBeenCalled());
    expect(screen.getByText("open")).toBeInTheDocument();
    expect(screen.getByLabelText("Paste JSON instead of a file")).toHaveValue(DOCUMENT);
  });

  it("says what is missing when nothing was chosen, and sends nothing", async () => {
    const user = userEvent.setup();
    render(<Harness />);

    await user.click(screen.getByRole("button", { name: "Import book" }));

    expect(await screen.findByText(/Choose a file, or paste JSON/)).toBeInTheDocument();
    expect(mutateAsync).not.toHaveBeenCalled();
  });
});
