import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { TooltipProvider } from "@/components/ui/tooltip";
import { type BuilderSource, TaxonomyBuilder } from "./taxonomy-builder";
import { draftFromVersion } from "./taxonomy-draft";
import { sampleDraft } from "./taxonomy-draft.fixtures";
import { loadDrafts, saveDraft } from "./taxonomy-draft-storage";

const mutateAsync = vi.fn();
const updateAsync = vi.fn();
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
  useUpdateCurriculumTree: () => ({
    mutateAsync: updateAsync,
    reset: vi.fn(),
    isPending: false,
    error: null,
  }),
}));

const APPROVED = {
  data: { version: { label: "Live taxonomy" }, topic_count: 4, subtopic_count: 11 },
};

const DRAFTS_KEY = "adaptive-trainer:taxonomy-drafts:v2";

/** Unsaved work being resumed, as the page hands it over from what is kept in the browser. */
const resumed = (draft = sampleDraft(), origin: BuilderSource["origin"] = null): BuilderSource => ({
  origin,
  draft,
  restoredAt: "2026-01-01T00:00:00.000Z",
});

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

/** A saved taxonomy, as the page hands it to the builder: its rows keep the ids they have. */
const copyOf = (id: number, label: string): BuilderSource => ({
  origin: { id, label },
  draft: draftFromVersion(label, [
    {
      id: 100,
      name: "Loops",
      description: null,
      subtopics: [
        { id: 101, name: "for loops", description: "Iterating." },
        { id: 102, name: "while loops", description: null },
      ],
    },
    {
      id: 200,
      name: "Functions",
      description: "Reusable.",
      subtopics: [{ id: 201, name: "Defining", description: null }],
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
  updateAsync.mockReset();
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
    expect(window.localStorage.getItem(DRAFTS_KEY)).toBeNull();
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
    await waitFor(() => expect(window.localStorage.getItem(DRAFTS_KEY)).toContain("while loops"));
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
    const user = userEvent.setup();
    renderScreen(resumed());
    await screen.findByText("Unsaved draft restored");

    await user.type(screen.getByLabelText("Search the outline"), "rebinding");

    const tree = screen.getByRole("tree");
    expect(within(tree).getByText(/Assignment and/)).toBeInTheDocument();
    expect(within(tree).queryByText("Loops")).not.toBeInTheDocument();
  });

  it("offers a restored draft, and discards it on request", async () => {
    saveDraft(sampleDraft());
    const user = userEvent.setup();
    renderScreen(resumed());

    expect(await screen.findByText("Unsaved draft restored")).toBeInTheDocument();
    expect(screen.getByLabelText("Taxonomy name")).toHaveValue("Introductory Python");

    await user.click(screen.getByRole("button", { name: "Discard draft" }));
    expect(screen.getByLabelText("Taxonomy name")).toHaveValue("");
    expect(loadDrafts()).toEqual([]);
  });

  it("answers `/` by focusing the search box", async () => {
    const user = userEvent.setup();
    renderScreen();

    await user.keyboard("/");
    expect(screen.getByLabelText("Search the outline")).toHaveFocus();
  });

  describe("editing a saved taxonomy", () => {
    it("fills the builder with the taxonomy and offers both ways of saving", async () => {
      renderScreen(copyOf(3, "Intro Python"));

      expect(await screen.findByLabelText("Taxonomy name")).toHaveValue("Intro Python");
      expect(screen.getByText(/^Editing/)).toHaveTextContent("Intro Python");
      const tree = screen.getByRole("tree");
      expect(within(tree).getByText("Loops")).toBeInTheDocument();
      expect(within(tree).getByText("for loops")).toBeInTheDocument();
      expect(within(tree).getByText("Functions")).toBeInTheDocument();
      expect(screen.getByRole("button", { name: "Save changes" })).toBeInTheDocument();
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
      expect(window.localStorage.getItem(DRAFTS_KEY)).toBeNull();
    });

    it("keeps an edited copy, together with the taxonomy it came from", async () => {
      const user = userEvent.setup();
      renderScreen(copyOf(3, "Intro Python"));
      await user.type(await screen.findByLabelText("Taxonomy name"), " v2");

      await waitFor(() => {
        const stored = loadDrafts().find((d) => d.key === "v3");
        expect(stored?.origin).toEqual({ id: 3, label: "Intro Python" });
        expect(stored?.draft.label).toBe("Intro Python v2");
      });
    });

    it("resumes an edited copy and says which taxonomy it belongs to", async () => {
      renderScreen(resumed(sampleDraft(), { id: 9, label: "Nine" }));

      expect(await screen.findByText("Unsaved draft restored")).toBeInTheDocument();
      expect(screen.getByText(/^Editing/)).toHaveTextContent("Nine");
    });

    it("saves as a new version, sending the edited document and not the original's", async () => {
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
      expect(updateAsync).not.toHaveBeenCalled();
    });

    it("does not send a copy out under the very name it was opened with", async () => {
      mutateAsync.mockResolvedValue({
        version: { id: 11, label: "Intro Python (copy)" },
        topic_count: 2,
        subtopic_count: 3,
      });
      const user = userEvent.setup();
      renderScreen(copyOf(3, "Intro Python"));
      await screen.findByLabelText("Taxonomy name");

      await user.click(screen.getByRole("button", { name: "Save as new version" }));

      await waitFor(() => expect(mutateAsync).toHaveBeenCalledTimes(1));
      const [[{ file }]] = mutateAsync.mock.calls as [[{ file: File }]];
      expect(JSON.parse(await file.text()).label).toBe("Intro Python (copy)");
    });

    it("saves changes to the same taxonomy in place, with the ids it already has and no confirmation", async () => {
      approved = APPROVED;
      updateAsync.mockResolvedValue({
        version: { id: 3, label: "Intro Python" },
        topic_count: 1,
        subtopic_count: 2,
      });
      const user = userEvent.setup();
      renderScreen(copyOf(3, "Intro Python"));
      await screen.findByLabelText("Taxonomy name");
      const tree = screen.getByRole("tree");
      await user.click(within(tree).getByRole("button", { name: "Remove topic Functions" }));

      await user.click(screen.getByRole("button", { name: "Save changes" }));

      await waitFor(() => expect(updateAsync).toHaveBeenCalledTimes(1));
      expect(mutateAsync).not.toHaveBeenCalled();
      expect(screen.queryByText("Make this the active taxonomy?")).not.toBeInTheDocument();
      const [[{ versionId, body }]] = updateAsync.mock.calls as [
        [
          {
            versionId: number;
            body: { label: string; topics: { id: number | null; name: string }[] };
          },
        ],
      ];
      expect(versionId).toBe(3);
      expect(body.label).toBe("Intro Python");
      // Functions is left out, which is how the server knows to hide it.
      expect(body.topics.map((t) => [t.id, t.name])).toEqual([[100, "Loops"]]);
      await waitFor(() => expect(callbacks.onSaved).toHaveBeenCalledTimes(1));
      expect(loadDrafts()).toEqual([]);
    });

    it("sends one edit however fast Save changes is clicked", async () => {
      let finish: (value: unknown) => void = () => {};
      updateAsync.mockReturnValue(new Promise((resolve) => (finish = resolve)));
      const user = userEvent.setup();
      renderScreen(copyOf(3, "Intro Python"));
      await screen.findByLabelText("Taxonomy name");
      const button = screen.getByRole("button", { name: "Save changes" });

      // Both clicks land before React has re-rendered the button as disabled.
      fireEvent.click(button);
      fireEvent.click(button);
      await user.click(button);

      expect(updateAsync).toHaveBeenCalledTimes(1);
      finish({ version: { id: 3, label: "Intro Python" }, topic_count: 2, subtopic_count: 3 });
      await waitFor(() => expect(callbacks.onSaved).toHaveBeenCalledTimes(1));
    });

    it("sends a topic added while editing without an id, so the server creates it", async () => {
      updateAsync.mockResolvedValue({
        version: { id: 3, label: "Intro Python" },
        topic_count: 3,
        subtopic_count: 4,
      });
      const user = userEvent.setup();
      renderScreen(copyOf(3, "Intro Python"));
      await screen.findByLabelText("Taxonomy name");
      await user.click(screen.getAllByRole("button", { name: /^Add topic$/ })[0] as HTMLElement);
      await user.type(await screen.findByLabelText("Topic name"), "Classes");
      await user.click(
        screen.getAllByRole("button", { name: /Add subtopic/ }).at(-1) as HTMLElement,
      );
      await user.type(await screen.findByLabelText("Subtopic 1 name"), "Methods");

      await user.click(screen.getByRole("button", { name: "Save changes" }));

      await waitFor(() => expect(updateAsync).toHaveBeenCalledTimes(1));
      const [[{ body }]] = updateAsync.mock.calls as [
        [
          {
            body: {
              topics: { id: number | null; name: string; subtopics: { id: number | null }[] }[];
            };
          },
        ],
      ];
      const added = body.topics.find((t) => t.name === "Classes");
      expect(added?.id).toBeNull();
      expect(added?.subtopics.map((s) => s.id)).toEqual([null]);
      expect(body.topics.filter((t) => t.id !== null).map((t) => t.id)).toEqual([100, 200]);
    });

    it("keeps the draft when the in-place save is refused", async () => {
      updateAsync.mockRejectedValue(new Error("refused"));
      const user = userEvent.setup();
      renderScreen(copyOf(3, "Intro Python"));
      await user.type(await screen.findByLabelText("Taxonomy name"), " v2");
      await waitFor(() => expect(loadDrafts().some((d) => d.key === "v3")).toBe(true));

      await user.click(screen.getByRole("button", { name: "Save changes" }));

      await waitFor(() => expect(updateAsync).toHaveBeenCalledTimes(1));
      expect(callbacks.onSaved).not.toHaveBeenCalled();
      expect(loadDrafts().some((d) => d.key === "v3")).toBe(true);
    });

    it("offers a new taxonomy only Save taxonomy: there is nothing to edit in place", async () => {
      renderScreen(resumed());
      await screen.findByLabelText("Taxonomy name");

      expect(screen.getByRole("button", { name: "Save taxonomy" })).toBeInTheDocument();
      expect(screen.queryByRole("button", { name: "Save changes" })).not.toBeInTheDocument();
    });

    it("replaces the previous draft completely when another copy is loaded", async () => {
      const user = userEvent.setup();
      const view = renderScreen(copyOf(3, "Intro Python"));
      await screen.findByLabelText("Taxonomy name");
      const tree = screen.getByRole("tree");
      await user.click(within(tree).getByRole("button", { name: "Remove topic Functions" }));
      await user.type(screen.getByLabelText("Search the outline"), "for");

      view.load(copyOf(4, "Other"));

      expect(await screen.findByDisplayValue("Other")).toBeInTheDocument();
      expect(screen.getByText(/^Editing/)).toHaveTextContent("Other");
      expect(screen.getByLabelText("Search the outline")).toHaveValue("");
      expect(within(screen.getByRole("tree")).getByText("Functions")).toBeInTheDocument();
      // The removal made on the previous draft cannot be "undone" into this one.
      expect(screen.getByRole("button", { name: /^Undo/ })).toBeDisabled();
    });

    it("never touches work kept for another taxonomy, whether the copy is left alone or edited", async () => {
      saveDraft({ ...sampleDraft(), label: "Someone else's" }, { id: 8, label: "Eight" });
      saveDraft({ ...sampleDraft(), label: "A new one" });
      const user = userEvent.setup();
      renderScreen(copyOf(3, "Intro Python"));
      await screen.findByLabelText("Taxonomy name");

      // Looking at a copy does not clear anything...
      await new Promise((resolve) => setTimeout(resolve, 600));
      expect(
        loadDrafts()
          .map((d) => d.key)
          .sort(),
      ).toEqual(["new", "v8"]);

      // ...and editing it writes only its own slot.
      await user.type(screen.getByLabelText("Taxonomy name"), " v2");
      await waitFor(() =>
        expect(
          loadDrafts()
            .map((d) => d.key)
            .sort(),
        ).toEqual(["new", "v3", "v8"]),
      );
      expect(loadDrafts().find((d) => d.key === "v8")?.draft.label).toBe("Someone else's");
      expect(loadDrafts().find((d) => d.key === "new")?.draft.label).toBe("A new one");
    });

    it("forgets its own kept draft when it is changed back to what was loaded", async () => {
      const user = userEvent.setup();
      renderScreen(copyOf(3, "Intro Python"));
      const name = await screen.findByLabelText("Taxonomy name");
      await user.type(name, "X");
      await waitFor(() => expect(loadDrafts().some((d) => d.key === "v3")).toBe(true));

      await user.type(name, "{Backspace}");

      await waitFor(() => expect(loadDrafts().some((d) => d.key === "v3")).toBe(false));
    });
  });
});
