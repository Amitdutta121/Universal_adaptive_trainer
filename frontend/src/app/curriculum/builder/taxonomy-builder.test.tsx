import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { TooltipProvider } from "@/components/ui/tooltip";
import { TaxonomyBuilder } from "./taxonomy-builder";
import { sampleDraft } from "./taxonomy-draft.fixtures";
import { saveDraft } from "./taxonomy-draft-storage";

const push = vi.fn();
const mutateAsync = vi.fn();
let approved: { data: unknown } = { data: undefined };

vi.mock("next/navigation", () => ({ useRouter: () => ({ push }) }));
vi.mock("sonner", () => ({
  toast: Object.assign(vi.fn(), { success: vi.fn(), dismiss: vi.fn() }),
}));
vi.mock("@/lib/api/queries", () => ({
  useTaxonomyDocumentGuide: () => ({
    data: {
      schema_version: "1",
      fields: [
        { path: "label", max_length: 200 },
        { path: "topics[].name", max_length: 300 },
      ],
    },
    error: null,
  }),
  useApprovedCurriculum: () => approved,
  useImportTaxonomy: () => ({ mutateAsync, reset: vi.fn(), isPending: false, error: null }),
}));

const APPROVED = {
  data: { version: { label: "Live taxonomy" }, topic_count: 4, subtopic_count: 11 },
};

function renderScreen() {
  return render(
    <TooltipProvider>
      <TaxonomyBuilder />
    </TooltipProvider>,
  );
}

/** Build a one-topic, one-subtopic taxonomy through the UI, the way a professor would. */
async function typeFinishedDraft(user: ReturnType<typeof userEvent.setup>) {
  await user.type(screen.getByLabelText("Taxonomy name"), "My taxonomy");
  await user.click(screen.getAllByRole("button", { name: /^Add topic$/ })[0] as HTMLElement);
  await user.type(await screen.findByLabelText("Topic name"), "Loops");
  await user.click(screen.getAllByRole("button", { name: /Add subtopic/ }).at(-1) as HTMLElement);
  await user.type(await screen.findByLabelText("Subtopic 1 name"), "while loops");
}

beforeEach(() => {
  window.localStorage.clear();
  push.mockReset();
  mutateAsync.mockReset();
  approved = { data: undefined };
});

describe("TaxonomyBuilder", () => {
  it("will not send an unfinished draft, and says what is missing", async () => {
    const user = userEvent.setup();
    renderScreen();

    await user.click(screen.getByRole("button", { name: /^Save taxonomy$/ }));

    expect(await screen.findByText("Not ready to save")).toBeInTheDocument();
    expect(
      screen.getByText(/name/i, { selector: "[data-slot=alert-description]" }),
    ).toBeInTheDocument();
    expect(mutateAsync).not.toHaveBeenCalled();
  });

  it("sends the taxonomy document the backend expects, then leaves for the new version", async () => {
    mutateAsync.mockResolvedValue({
      version: { id: 7, label: "My taxonomy" },
      topic_count: 1,
      subtopic_count: 1,
    });
    const user = userEvent.setup();
    renderScreen();
    await typeFinishedDraft(user);

    await user.click(screen.getByRole("button", { name: /^Save taxonomy$/ }));

    await waitFor(() => expect(mutateAsync).toHaveBeenCalledTimes(1));
    const [[{ file }]] = mutateAsync.mock.calls as [[{ file: File }]];
    expect(file.name).toBe("manual-taxonomy.json");
    expect(JSON.parse(await file.text())).toEqual({
      schema_version: "1",
      label: "My taxonomy",
      topics: [
        { name: "Loops", description: "", subtopics: [{ name: "while loops", description: "" }] },
      ],
    });
    await waitFor(() => expect(push).toHaveBeenCalledWith("/curriculum/versions/7"));
    expect(window.localStorage.getItem("adaptive-trainer:taxonomy-draft:v1")).toBeNull();
  });

  it("asks before replacing the live taxonomy, and sends nothing until told to", async () => {
    approved = APPROVED;
    mutateAsync.mockResolvedValue({
      version: { id: 8, label: "My taxonomy" },
      topic_count: 1,
      subtopic_count: 1,
    });
    const user = userEvent.setup();
    renderScreen();
    await typeFinishedDraft(user);

    await user.click(screen.getByRole("button", { name: /^Save taxonomy$/ }));

    const dialog = await screen.findByRole("dialog");
    expect(within(dialog).getByText("Live taxonomy")).toBeInTheDocument();
    expect(mutateAsync).not.toHaveBeenCalled();

    await user.click(within(dialog).getByRole("button", { name: "Save and make active" }));
    await waitFor(() => expect(mutateAsync).toHaveBeenCalledTimes(1));
  });

  it("keeps the draft when the backend refuses it", async () => {
    mutateAsync.mockRejectedValue(new Error("refused"));
    const user = userEvent.setup();
    renderScreen();
    await typeFinishedDraft(user);

    await user.click(screen.getByRole("button", { name: /^Save taxonomy$/ }));

    await waitFor(() => expect(mutateAsync).toHaveBeenCalled());
    expect(push).not.toHaveBeenCalled();
    expect(screen.getByLabelText("Taxonomy name")).toHaveValue("My taxonomy");
    // Autosave is debounced; it must still land after a refused save.
    await waitFor(() =>
      expect(window.localStorage.getItem("adaptive-trainer:taxonomy-draft:v1")).toContain(
        "while loops",
      ),
    );
  });

  it("removes at once and puts the item back on Undo", async () => {
    const user = userEvent.setup();
    renderScreen();
    await typeFinishedDraft(user);
    const tree = screen.getByRole("tree");

    await user.click(within(tree).getByRole("button", { name: "Remove topic Loops" }));
    expect(within(screen.getByRole("tree")).queryByText("Loops")).not.toBeInTheDocument();

    await user.click(screen.getByRole("button", { name: /^Undo/ }));
    expect(within(screen.getByRole("tree")).getByText("Loops")).toBeInTheDocument();
    expect(within(screen.getByRole("tree")).getByText("while loops")).toBeInTheDocument();
  });

  it("filters the outline as you search", async () => {
    saveDraft(sampleDraft());
    const user = userEvent.setup();
    renderScreen();
    await screen.findByText("Unsaved draft restored");

    await user.type(screen.getByLabelText("Search the outline"), "rebinding");

    const tree = screen.getByRole("tree");
    expect(within(tree).getByText(/Assignment and/)).toBeInTheDocument();
    expect(within(tree).queryByText("Loops")).not.toBeInTheDocument();
  });

  it("offers a restored draft, and discards it on request", async () => {
    saveDraft(sampleDraft());
    const user = userEvent.setup();
    renderScreen();

    expect(await screen.findByText("Unsaved draft restored")).toBeInTheDocument();
    expect(screen.getByLabelText("Taxonomy name")).toHaveValue("Introductory Python");

    await user.click(screen.getByRole("button", { name: "Discard draft" }));
    expect(screen.getByLabelText("Taxonomy name")).toHaveValue("");
    expect(window.localStorage.getItem("adaptive-trainer:taxonomy-draft:v1")).toBeNull();
  });

  it("answers `/` by focusing the search box", async () => {
    const user = userEvent.setup();
    renderScreen();

    await user.keyboard("/");
    expect(screen.getByLabelText("Search the outline")).toHaveFocus();
  });
});
