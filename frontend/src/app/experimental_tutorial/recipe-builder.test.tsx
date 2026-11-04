import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render as baseRender, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { RecipeBuilder } from "./recipe-builder";

function render(ui: React.ReactElement) {
  return baseRender(<QueryClientProvider client={new QueryClient()}>{ui}</QueryClientProvider>);
}

const draftMutate = vi.fn();
const saveMutate = vi.fn();
const deleteMutate = vi.fn();
/** `mutate(vars, { onSuccess })` over a mocked async mutation, as React Query calls it. */
const asMutate =
  (fn: (vars: unknown) => unknown) =>
  (vars: unknown, options?: { onSuccess?: (result: unknown) => void }) =>
    void Promise.resolve(fn(vars)).then((result) => options?.onSuccess?.(result));
const tryMutate = vi.fn();
const exampleQuery = vi.fn();
const state = vi.hoisted(() => ({ recipes: [] as unknown[], drafting: false }));

const YAML = "id: exp.analogy\nname: Analogy\nsummary: One analogy.\nrenderer: markdown\n";
const PARSED = {
  id: "exp.analogy",
  subject: "intro_python",
  name: "One analogy and its limit",
  summary: "An everyday analogy, then where it breaks.",
  renderer: "markdown",
  prompt: "Write an analogy.",
  fits: ["concept"],
  guidance_levels: ["cue", "worked"],
  inputs: ["subtopic", "chunks"],
  tool: null,
  checks: [],
};
const CURRICULUM = {
  topics: [
    { name: "Loops", subtopics: [{ id: 11, name: "for loops" }] },
    { name: "Functions", subtopics: [{ id: 21, name: "return values" }] },
  ],
};

vi.mock("@/components/page-header", () => ({
  PageHeader: ({ title }: { title: string }) => <h1>{title}</h1>,
}));
vi.mock("@/components/tutorial/renderer-registry", () => ({
  TutorialBlockView: ({ payload }: { payload: { markdown: string } }) => <p>{payload.markdown}</p>,
}));

vi.mock("@/lib/api/queries", () => ({
  useCourses: () => ({
    isPending: false,
    isError: false,
    isSuccess: true,
    data: {
      courses: [
        { id: 3, name: "Empty", curriculum_version_count: 0 },
        { id: 7, name: "CS115", curriculum_version_count: 1 },
      ],
    },
  }),
  useExperimentalRecipes: () => ({
    isPending: false,
    isError: false,
    isSuccess: true,
    data: state.recipes,
  }),
  useExperimentalCurriculum: () => ({ isError: false, data: CURRICULUM }),
  useModelSettings: () => ({
    data: {
      roles: [
        {
          role: "tutorials",
          provider: "openrouter",
          model: "gpt-5-mini",
          base_url: "https://lab.services.ai.azure.com/openai/v1/",
        },
      ],
    },
  }),
  useDraftExperimentalRecipe: () => ({
    mutateAsync: draftMutate,
    isPending: state.drafting,
    error: null,
    data: undefined,
  }),
  useSaveExperimentalRecipe: () => ({
    mutateAsync: saveMutate,
    mutate: asMutate(saveMutate),
    isPending: false,
    error: null,
  }),
  useDeleteExperimentalRecipe: () => ({
    mutateAsync: deleteMutate,
    mutate: asMutate(deleteMutate),
    isPending: false,
    error: null,
  }),
  useExperimentalExample: (courseId: number, run: number, body: unknown) => {
    exampleQuery(courseId, run, body);
    return {
      isPending: false,
      error: null,
      data: {
        renderer: "markdown",
        payload: { markdown: "Example block" },
        chunk_ids: ["c1"],
        error: null,
        model: "azure/gpt-5-mini",
        guidance_level: "cue",
      },
    };
  },
  useTryExperimentalRecipe: () => ({
    mutate: tryMutate,
    isPending: false,
    error: null,
    data: null,
  }),
}));

beforeEach(() => {
  draftMutate.mockReset();
  saveMutate.mockReset();
  deleteMutate.mockReset();
  tryMutate.mockReset();
  exampleQuery.mockReset();
  state.recipes = [];
  state.drafting = false;
});

describe("RecipeBuilder", () => {
  it("keeps the request, shows the recipe readably and generates two examples", async () => {
    draftMutate.mockResolvedValue({ yaml: YAML, problems: [], recipe: PARSED });
    const user = userEvent.setup();
    render(<RecipeBuilder />);

    await user.type(screen.getByLabelText("Describe the style"), "Teach with an analogy");
    await user.click(screen.getByRole("button", { name: "Draft with AI" }));

    // The course with a curriculum is picked by default.
    expect(draftMutate).toHaveBeenCalledWith({
      courseId: 7,
      body: { description: "Teach with an analogy", current_yaml: null },
    });
    expect(screen.getByText("What you asked for")).toBeInTheDocument();
    expect(screen.getByText("Teach with an analogy")).toBeInTheDocument();
    expect(await screen.findByText("One analogy and its limit")).toBeInTheDocument();
    // The YAML is one click away, not the main view.
    expect(screen.queryByLabelText("Style YAML")).not.toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Edit YAML" }));
    expect(screen.getByLabelText("Style YAML")).toHaveValue(YAML);

    // Two examples on subtopics of different topics, at the recipe's first level, shown.
    expect(await screen.findAllByText("Example block")).toHaveLength(2);
    const asked = exampleQuery.mock.calls.map(([, run, body]) => ({ run, ...body }));
    expect(new Set(asked.map((call) => call.subtopic_id))).toEqual(new Set([11, 21]));
    expect(asked.every((call) => call.run === 1 && call.guidance_level === "cue")).toBe(true);
  });

  it("says inline where it is generating, without blocking the page", () => {
    state.drafting = true;
    render(<RecipeBuilder />);

    const status = screen.getByRole("status");
    expect(status).toHaveTextContent("Generating the style on Azure · gpt-5-mini");
    expect(screen.getByRole("button", { name: /New/ })).toBeEnabled();
  });

  it("opens a saved recipe for editing and deletes it", async () => {
    state.recipes = [
      {
        id: 3,
        recipe_id: "exp.analogy",
        name: "Analogy",
        summary: "One analogy.",
        renderer: "markdown",
        yaml: YAML,
        updated_at: "2026-10-22T10:00:00Z",
        recipe: PARSED,
      },
    ];
    deleteMutate.mockResolvedValue(undefined);
    const user = userEvent.setup();
    render(<RecipeBuilder />);

    await user.click(screen.getByRole("button", { name: /^Analogy/ }));
    expect(screen.getByText("One analogy and its limit")).toBeInTheDocument();
    // A saved recipe's examples cost a call each, so they wait for a click.
    expect(exampleQuery).not.toHaveBeenCalled();
    const examples = screen.getByText("Examples").closest("div")?.parentElement as HTMLElement;
    await user.click(within(examples).getByRole("button", { name: "Show 2 examples" }));
    expect(await screen.findAllByText("Example block")).toHaveLength(2);

    await user.click(screen.getByRole("button", { name: "Delete" }));
    expect(deleteMutate).toHaveBeenCalledWith({ courseId: 7, id: 3 });
  });
});
