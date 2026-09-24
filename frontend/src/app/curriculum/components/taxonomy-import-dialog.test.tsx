import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { useState } from "react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { TaxonomyImportDialog } from "./taxonomy-import-dialog";

const mutateAsync = vi.fn();

vi.mock("sonner", () => ({ toast: { success: vi.fn() } }));
// The guide's own card is not what is under test here.
vi.mock("./taxonomy-guide-card", () => ({ TaxonomyGuideCard: () => <div>guide card</div> }));
vi.mock("@/lib/api/queries", () => ({
  useTaxonomyDocumentGuide: () => ({
    data: { schema_version: "1", supported_extensions: [".json"], max_upload_mb: 5 },
    isPending: false,
    error: null,
  }),
  useImportTaxonomy: () => ({ mutateAsync, reset: vi.fn(), isPending: false, error: null }),
}));

function Harness() {
  const [open, setOpen] = useState(true);
  return (
    <>
      <span>{open ? "open" : "closed"}</span>
      <TaxonomyImportDialog open={open} onOpenChange={setOpen} />
    </>
  );
}

const DOCUMENT = '{"schema_version":"1","label":"L","topics":[]}';

beforeEach(() => {
  // Braces matter: a function returned from beforeEach is run as teardown, and mockReset() returns the mock.
  mutateAsync.mockReset();
});

describe("TaxonomyImportDialog", () => {
  it("imports pasted JSON as a document and closes on success", async () => {
    mutateAsync.mockResolvedValue({ version: { label: "L" }, topic_count: 1, subtopic_count: 2 });
    const user = userEvent.setup();
    render(<Harness />);

    await user.click(screen.getByRole("tab", { name: "Paste JSON" }));
    await user.click(screen.getByLabelText("Taxonomy JSON document"));
    await user.paste(DOCUMENT);
    await user.click(screen.getByRole("button", { name: "Import taxonomy" }));

    await waitFor(() => expect(mutateAsync).toHaveBeenCalledTimes(1));
    const [[{ file }]] = mutateAsync.mock.calls as [[{ file: File }]];
    expect(file.name).toBe("pasted-taxonomy.json");
    expect(await file.text()).toBe(DOCUMENT);
    await waitFor(() => expect(screen.getByText("closed")).toBeInTheDocument());
  });

  it("stays open with the text intact when the document is refused", async () => {
    mutateAsync.mockRejectedValue(new Error("refused"));
    const user = userEvent.setup();
    render(<Harness />);

    await user.click(screen.getByRole("tab", { name: "Paste JSON" }));
    await user.click(screen.getByLabelText("Taxonomy JSON document"));
    await user.paste(DOCUMENT);
    await user.click(screen.getByRole("button", { name: "Import taxonomy" }));

    await waitFor(() => expect(mutateAsync).toHaveBeenCalled());
    expect(screen.getByText("open")).toBeInTheDocument();
    expect(screen.getByLabelText("Taxonomy JSON document")).toHaveValue(DOCUMENT);
  });

  it("does not send text that is not JSON, and says why", async () => {
    const user = userEvent.setup();
    render(<Harness />);

    await user.click(screen.getByRole("tab", { name: "Paste JSON" }));
    await user.click(screen.getByLabelText("Taxonomy JSON document"));
    await user.paste("not json");
    await user.click(screen.getByRole("button", { name: "Import taxonomy" }));

    expect(await screen.findByText(/not valid JSON/i)).toBeInTheDocument();
    expect(mutateAsync).not.toHaveBeenCalled();
  });
});
