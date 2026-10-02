import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { useState } from "react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { TooltipProvider } from "@/components/ui/tooltip";
import { sampleDraft } from "./builder/taxonomy-draft.fixtures";
import { loadDrafts, saveDraft } from "./builder/taxonomy-draft-storage";
import { CurriculumScreen } from "./curriculum-screen";

const summary = (id: number, label: string) => ({
  id,
  label,
  status: "approved",
  generated_by: "taxonomy-upload",
  source_book_ids: [],
  created_at: "2026-09-23T10:00:00Z",
  approved_at: "2026-09-23T10:00:00Z",
  topic_count: 1,
  subtopic_count: 2,
});

const fetchQuery = vi.fn();

vi.mock("sonner", () => ({
  toast: Object.assign(vi.fn(), { success: vi.fn(), error: vi.fn(), dismiss: vi.fn() }),
}));
vi.mock("@tanstack/react-query", () => ({ useQueryClient: () => ({ fetchQuery }) }));
// The URL-backed filters are not what is under test; keep them as plain state.
vi.mock("nuqs", () => {
  const parser = { withDefault: (value: unknown) => ({ defaultValue: value }) };
  return {
    parseAsString: parser,
    parseAsStringLiteral: () => parser,
    useQueryState: (_key: string, options?: { defaultValue?: unknown }) =>
      useState(options?.defaultValue ?? null),
  };
});
vi.mock("@/components/page-header", () => ({ PageHeader: () => <h1>Curriculum</h1> }));
vi.mock("./components/taxonomy-import-dialog", () => ({ TaxonomyImportDialog: () => null }));
vi.mock("./components/version-edit-dialog", () => ({ VersionEditDialog: () => null }));
vi.mock("./components/version-delete-dialog", () => ({ VersionDeleteDialog: () => null }));
vi.mock("@/lib/api/queries", () => ({
  curriculumVersionQuery: (id: number) => ({ queryKey: ["version", id] }),
  // The builder modal still reads it.
  useApprovedCurriculum: () => ({ data: undefined, isPending: false, error: null }),
  useCurriculumVersions: () => ({
    data: {
      versions: [summary(2, "Newer"), summary(1, "Older")],
      approved_version_id: 2,
      total: 2,
    },
    isPending: false,
    isError: false,
    isSuccess: true,
  }),
  useActivateCurriculumVersion: () => ({ mutateAsync: vi.fn(), isPending: false }),
  useTaxonomyDocumentGuide: () => ({
    data: { schema_version: "1", fields: [] },
    error: null,
  }),
  useImportTaxonomy: () => ({
    mutateAsync: vi.fn(),
    reset: vi.fn(),
    isPending: false,
    error: null,
  }),
  useUpdateCurriculumTree: () => ({
    mutateAsync: vi.fn(),
    reset: vi.fn(),
    isPending: false,
    error: null,
  }),
}));

const DETAIL = {
  version: { id: 1, label: "Older" },
  topics: [
    {
      name: "Loops",
      description: null,
      subtopics: [
        { name: "for loops", description: "Iterating." },
        { name: "while loops", description: null },
      ],
    },
  ],
};

function renderScreen() {
  return render(
    <TooltipProvider>
      <CurriculumScreen />
    </TooltipProvider>,
  );
}

const modal = () => screen.findByRole("dialog", { name: "Taxonomy builder" });

beforeEach(() => {
  window.localStorage.clear();
  fetchQuery.mockReset();
  fetchQuery.mockResolvedValue(DETAIL);
});

describe("CurriculumScreen", () => {
  it("shows the taxonomies as a table and nothing else editable on the page", () => {
    renderScreen();

    expect(screen.getByRole("table", { name: "Saved taxonomies" })).toBeInTheDocument();
    expect(screen.queryByRole("tree")).not.toBeInTheDocument();
    expect(screen.queryByLabelText("Taxonomy name")).not.toBeInTheDocument();
  });

  it("opens a row in the builder modal, to edit in place or save as a new version", async () => {
    const user = userEvent.setup();
    renderScreen();

    await user.click(screen.getByText("Older"));

    const dialog = await modal();
    expect(fetchQuery).toHaveBeenCalledWith(expect.objectContaining({ queryKey: ["version", 1] }));
    expect(within(dialog).getByLabelText("Taxonomy name")).toHaveValue("Older");
    expect(within(dialog).getByText(/^Editing/)).toHaveTextContent("Older");
    const tree = within(dialog).getByRole("tree");
    expect(within(tree).getByText("Loops")).toBeInTheDocument();
    expect(within(tree).getByText("while loops")).toBeInTheDocument();
  });

  it("opens the same modal from a row's Preview button", async () => {
    const user = userEvent.setup();
    renderScreen();

    await user.click(screen.getByRole("button", { name: "Preview Older" }));

    expect(await modal()).toBeInTheDocument();
    expect(fetchQuery).toHaveBeenCalledTimes(1);
  });

  it("opens a blank builder from New taxonomy", async () => {
    const user = userEvent.setup();
    renderScreen();

    await user.click(screen.getByRole("button", { name: "New taxonomy" }));

    const dialog = await modal();
    expect(within(dialog).getByLabelText("Taxonomy name")).toHaveValue("");
    expect(within(dialog).getByText("New taxonomy")).toBeInTheDocument();
    expect(fetchQuery).not.toHaveBeenCalled();
  });

  it("closes an untouched builder straight away", async () => {
    const user = userEvent.setup();
    renderScreen();
    await user.click(screen.getByText("Older"));
    await modal();

    await user.keyboard("{Escape}");

    await waitFor(() => expect(screen.queryByRole("dialog")).not.toBeInTheDocument());
  });

  it("asks before closing a builder with unsaved changes, and keeps them if told to", async () => {
    const user = userEvent.setup();
    renderScreen();
    await user.click(screen.getByText("Older"));
    const dialog = await modal();
    await user.type(within(dialog).getByLabelText("Taxonomy name"), " v2");

    await user.keyboard("{Escape}");

    expect(await screen.findByText("Discard your changes?")).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Keep editing" }));
    expect(within(await modal()).getByLabelText("Taxonomy name")).toHaveValue("Older v2");
  });

  it("drops the changes, and the kept draft, when told to discard", async () => {
    const user = userEvent.setup();
    renderScreen();
    await user.click(screen.getByText("Older"));
    const dialog = await modal();
    await user.type(within(dialog).getByLabelText("Taxonomy name"), " v2");
    await waitFor(() => expect(loadDrafts()).toHaveLength(1));

    await user.keyboard("{Escape}");
    await user.click(await screen.findByRole("button", { name: "Discard changes" }));

    await waitFor(() => expect(screen.queryByRole("dialog")).not.toBeInTheDocument());
    expect(loadDrafts()).toEqual([]);
    expect(screen.queryByText(/Unsaved taxonomy/)).not.toBeInTheDocument();
  });

  it("says a load failed and opens nothing", async () => {
    fetchQuery.mockRejectedValue(new Error("down"));
    const user = userEvent.setup();
    renderScreen();

    await user.click(screen.getByText("Older"));

    const { toast } = await import("sonner");
    await waitFor(() => expect(toast.error).toHaveBeenCalled());
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
  });

  describe("with a taxonomy left unsaved in this browser", () => {
    beforeEach(() => saveDraft(sampleDraft(), { id: 1, label: "Older" }));

    it("offers to continue it, naming where it came from", async () => {
      renderScreen();

      expect(
        await screen.findByText(/Unsaved taxonomy: “Introductory Python”/),
      ).toBeInTheDocument();
      expect(screen.getByText(/Changes to “Older”/)).toBeInTheDocument();
    });

    it("continues it in the builder, restored as it was", async () => {
      const user = userEvent.setup();
      renderScreen();

      await user.click(await screen.findByRole("button", { name: "Continue editing" }));

      const dialog = await modal();
      expect(within(dialog).getByLabelText("Taxonomy name")).toHaveValue("Introductory Python");
      expect(within(dialog).getByText("Unsaved draft restored")).toBeInTheDocument();
      expect(within(dialog).getByText(/^Editing/)).toHaveTextContent("Older");
      expect(fetchQuery).not.toHaveBeenCalled();
    });

    it("discards it on request", async () => {
      const user = userEvent.setup();
      renderScreen();

      await user.click(await screen.findByRole("button", { name: "Discard" }));

      expect(screen.queryByText(/Unsaved taxonomy/)).not.toBeInTheDocument();
      expect(loadDrafts()).toEqual([]);
    });

    it("never asks anything before previewing a row or starting a new one, and leaves the kept work alone", async () => {
      const user = userEvent.setup();
      renderScreen();
      await screen.findByText(/Unsaved taxonomy/);

      await user.click(screen.getByText("Older"));
      const first = await modal();
      expect(within(first).getByLabelText("Taxonomy name")).toHaveValue("Older");
      expect(within(first).queryByText("Unsaved draft restored")).not.toBeInTheDocument();
      expect(screen.queryByText(/Replace your unsaved/)).not.toBeInTheDocument();

      await user.keyboard("{Escape}");
      await waitFor(() => expect(screen.queryByRole("dialog")).not.toBeInTheDocument());
      expect(await screen.findByText(/Unsaved taxonomy/)).toBeInTheDocument();

      await user.click(screen.getByRole("button", { name: "New taxonomy" }));
      expect(within(await modal()).getByLabelText("Taxonomy name")).toHaveValue("");
      expect(screen.queryByText(/Replace your unsaved/)).not.toBeInTheDocument();
      expect(loadDrafts()).toHaveLength(1);
    });

    it("leaves work kept for another taxonomy alone when changes to this one are discarded", async () => {
      const user = userEvent.setup();
      renderScreen();
      await screen.findByText(/Unsaved taxonomy/);
      await user.click(screen.getByText("Newer"));
      const dialog = await modal();
      await user.type(within(dialog).getByLabelText("Taxonomy name"), " x");
      await waitFor(() => expect(loadDrafts()).toHaveLength(2));
      await user.keyboard("{Escape}");

      await user.click(await screen.findByRole("button", { name: "Discard changes" }));

      await waitFor(() => expect(screen.queryByRole("dialog")).not.toBeInTheDocument());
      expect(loadDrafts().map((d) => d.key)).toEqual(["v1"]);
    });
  });

  it("offers each unsaved taxonomy separately, and discarding one leaves the other", async () => {
    saveDraft({ ...sampleDraft(), label: "First" }, { id: 1, label: "Older" });
    saveDraft({ ...sampleDraft(), label: "Second" });
    const user = userEvent.setup();
    renderScreen();

    expect(await screen.findByText(/Unsaved taxonomy: “First”/)).toBeInTheDocument();
    expect(screen.getByText(/Unsaved taxonomy: “Second”/)).toBeInTheDocument();

    const [discardFirst] = screen.getAllByRole("button", { name: "Discard" });
    await user.click(discardFirst as HTMLElement);

    expect(loadDrafts()).toHaveLength(1);
    expect(screen.getAllByText(/Unsaved taxonomy:/)).toHaveLength(1);
  });
});
