import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { TooltipProvider } from "@/components/ui/tooltip";
import { type BuilderSource, TaxonomyBuilder } from "./taxonomy-builder";
import { draftFromVersion } from "./taxonomy-draft";
import { sampleDraft } from "./taxonomy-draft.fixtures";
import { saveDraft } from "./taxonomy-draft-storage";

const mutateAsync = vi.fn();
let approved: { data: unknown } = { data: undefined };

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

const callbacks = { onDirtyChange: vi.fn(), onSaved: vi.fn() };

function renderScreen(source: BuilderSource | null = null) {
  const ui = (next: BuilderSource | null) => (
    <TooltipProvider>
      <TaxonomyBuilder source={next} {...callbacks} />
    </TooltipProvider>
  );
  const view = render(ui(source));
  return { ...view, load: (next: BuilderSource) => view.rerender(ui(next)) };
}

/** A copy of a saved taxonomy, as the page hands it to the builder. */
const copyOf = (id: number, label: string): BuilderSource => ({
  origin: { id, label },
  draft: draftFromVersion(`${label} (copy)`, [
    {
      name: "Loops",
      description: null,
      subtopics: [
        { name: "for loops", description: "Iterating." },
        { name: "while loops", description: null },
      ],
    },
    {
      name: "Functions",
      description: "Reusable.",
      subtopics: [{ name: "Defining", description: null }],
    },
  ]),
});

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
  for (const fn of Object.values(callbacks)) fn.mockReset();
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

  it("sends the taxonomy document the backend expects, then hands the new version to the page", async () => {
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
    await waitFor(() => expect(callbacks.onSaved).toHaveBeenCalledTimes(1));
    expect(callbacks.onSaved.mock.calls[0]?.[0].version.id).toBe(7);
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
    expect(callbacks.onSaved).not.toHaveBeenCalled();
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

  describe("editing a copy of a saved taxonomy", () => {
    it("fills the builder with the copy and says what saving will do", async () => {
      renderScreen(copyOf(3, "Intro Python"));

      expect(await screen.findByLabelText("Taxonomy name")).toHaveValue("Intro Python (copy)");
      expect(screen.getByText(/Editing a copy of/)).toHaveTextContent("Intro Python");
      const tree = screen.getByRole("tree");
      expect(within(tree).getByText("Loops")).toBeInTheDocument();
      expect(within(tree).getByText("for loops")).toBeInTheDocument();
      expect(within(tree).getByText("Functions")).toBeInTheDocument();
      expect(screen.getByRole("button", { name: "Save as new version" })).toBeInTheDocument();
    });

    it("is not dirty until something changes, and not dirty again once it is changed back", async () => {
      const user = userEvent.setup();
      renderScreen(copyOf(3, "Intro Python"));
      await screen.findByLabelText("Taxonomy name");
      await waitFor(() => expect(callbacks.onDirtyChange).toHaveBeenLastCalledWith(false));

      const name = screen.getByLabelText("Taxonomy name");
      await user.type(name, "X");
      await waitFor(() => expect(callbacks.onDirtyChange).toHaveBeenLastCalledWith(true));
      await user.type(name, "{Backspace}");
      await waitFor(() => expect(callbacks.onDirtyChange).toHaveBeenLastCalledWith(false));
    });

    it("keeps nothing in the browser for a copy nobody changed, so a reload does not offer it back", async () => {
      renderScreen(copyOf(3, "Intro Python"));
      await screen.findByLabelText("Taxonomy name");

      await new Promise((resolve) => setTimeout(resolve, 600));
      expect(window.localStorage.getItem("adaptive-trainer:taxonomy-draft:v1")).toBeNull();
    });

    it("keeps an edited copy, together with the taxonomy it came from", async () => {
      const user = userEvent.setup();
      renderScreen(copyOf(3, "Intro Python"));
      await user.type(await screen.findByLabelText("Taxonomy name"), " v2");

      await waitFor(() => {
        const raw = window.localStorage.getItem("adaptive-trainer:taxonomy-draft:v1");
        const stored = JSON.parse(raw ?? "null");
        expect(stored?.origin).toEqual({ id: 3, label: "Intro Python" });
        expect(stored?.draft.label).toBe("Intro Python (copy) v2");
      });
    });

    it("restores an edited copy on the next visit and says which taxonomy it belongs to", async () => {
      saveDraft(sampleDraft(), { id: 9, label: "Nine" });
      renderScreen();

      expect(await screen.findByText("Unsaved draft restored")).toBeInTheDocument();
      expect(screen.getByText(/Editing a copy of/)).toHaveTextContent("Nine");
    });

    it("saves the copy as a new version, sending the edited document and not the original's", async () => {
      mutateAsync.mockResolvedValue({
        version: { id: 11, label: "Renamed" },
        topic_count: 2,
        subtopic_count: 3,
      });
      const user = userEvent.setup();
      renderScreen(copyOf(3, "Intro Python"));
      const name = await screen.findByLabelText("Taxonomy name");
      await user.clear(name);
      await user.type(name, "Renamed");

      await user.click(screen.getByRole("button", { name: "Save as new version" }));

      await waitFor(() => expect(mutateAsync).toHaveBeenCalledTimes(1));
      const [[{ file }]] = mutateAsync.mock.calls as [[{ file: File }]];
      const sent = JSON.parse(await file.text());
      expect(sent.label).toBe("Renamed");
      expect(sent.topics.map((t: { name: string }) => t.name)).toEqual(["Loops", "Functions"]);
      expect(sent.topics[0].subtopics[1]).toEqual({ name: "while loops", description: "" });
      await waitFor(() => expect(callbacks.onSaved).toHaveBeenCalledTimes(1));
    });

    it("replaces the previous draft completely when another copy is loaded", async () => {
      const user = userEvent.setup();
      const view = renderScreen(copyOf(3, "Intro Python"));
      await screen.findByLabelText("Taxonomy name");
      const tree = screen.getByRole("tree");
      await user.click(within(tree).getByRole("button", { name: "Remove topic Functions" }));
      await user.type(screen.getByLabelText("Search the outline"), "for");

      view.load(copyOf(4, "Other"));

      expect(await screen.findByDisplayValue("Other (copy)")).toBeInTheDocument();
      expect(screen.getByText(/Editing a copy of/)).toHaveTextContent("Other");
      expect(screen.getByLabelText("Search the outline")).toHaveValue("");
      expect(within(screen.getByRole("tree")).getByText("Functions")).toBeInTheDocument();
      // The removal made on the previous draft cannot be "undone" into this one.
      expect(screen.getByRole("button", { name: /^Undo/ })).toBeDisabled();
    });
  });
});
