import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";

vi.mock("sonner", () => ({ toast: { success: vi.fn(), error: vi.fn() } }));
vi.mock("@/lib/use-course", () => ({ useCourseId: () => 1 }));
vi.mock("@/app/experimental_tutorial/recipe-builder", () => ({
  RecipeEditorDialog: () => <div>recipe editor</div>,
}));
vi.mock("@/components/tutorial/renderer-registry", () => ({
  TutorialBlockView: ({ payload }: { payload: { text: string } }) => <p>{payload.text}</p>,
}));

const recipe = {
  id: "py.trace",
  subject: "intro_python",
  name: "Step through the code",
  summary: "Walks a snippet line by line.",
  renderer: "html",
  prompt: "Write a stepper.",
  fits: ["code_behavior"],
  guidance_levels: ["worked", "faded"],
};
const block = (id: number, subtopic_id: number, guidance_level: string, text: string) => ({
  id,
  subtopic_id,
  recipe_id: recipe.id,
  guidance_level,
  renderer: "markdown",
  payload: { text },
  chunk_ids: [],
  status: "draft",
  error: null,
  model: "m",
  created_at: "2026-11-01T00:00:00Z",
});
const gallery = [
  block(3, 10, "worked", "loops worked"),
  block(2, 11, "faded", "lists faded"),
  block(1, 11, "worked", "lists worked"),
];

const decide = vi.fn();
const retire = vi.fn();
vi.mock("@/lib/api/queries", () => ({
  useTutorialRecipes: () => ({
    isPending: false,
    isError: false,
    data: { subject: "intro_python", recipes: [recipe], decisions: {}, stats: {}, live: true },
  }),
  useExperimentalRecipes: () => ({ data: [] }),
  usePregenerateTutorials: () => ({ mutateAsync: vi.fn(), isPending: false }),
  useDecideTutorialRecipe: () => ({ mutateAsync: decide, isPending: false }),
  useRetireTutorialBlock: () => ({ mutateAsync: retire, isPending: false }),
  useTutorialSample: () => ({ isPending: false, isError: false, data: gallery.slice(0, 1) }),
  useTutorialGallery: () => ({ isPending: false, isError: false, data: gallery }),
}));

import { RecipeApproval } from "./recipe-approval";

const names = new Map([
  [10, "For loops"],
  [11, "Lists"],
]);

beforeEach(() => {
  decide.mockReset();
  decide.mockResolvedValue({ blocks_changed: 2 });
  retire.mockReset();
  retire.mockResolvedValue({});
});

describe("RecipeApproval", () => {
  it("opens a style in a modal with its details and examples", async () => {
    render(<RecipeApproval versionId={5} subtopicNames={names} />);
    await userEvent.click(screen.getByRole("button", { name: /Step through the code/ }));

    const dialog = screen.getByRole("dialog");
    expect(within(dialog).getByText("Interactive")).toBeInTheDocument();
    expect(within(dialog).getByText("Worked example, Faded")).toBeInTheDocument();
    expect(within(dialog).getByText("loops worked")).toBeInTheDocument();
    expect(within(dialog).queryByText("lists faded")).not.toBeInTheDocument();

    await userEvent.click(within(dialog).getByRole("switch"));
    expect(decide).toHaveBeenCalledWith({
      recipeId: "py.trace",
      curriculum_version_id: 5,
      approved: false,
    });
  });

  it("turns a style on or off from its card, without opening it", async () => {
    render(<RecipeApproval versionId={5} subtopicNames={names} />);
    const toggle = screen.getByRole("switch", { name: "Turn off Step through the code" });
    expect(toggle).toHaveAttribute("aria-checked", "true");

    await userEvent.click(toggle);
    expect(decide).toHaveBeenCalledWith({
      recipeId: "py.trace",
      curriculum_version_id: 5,
      approved: false,
    });
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
  });

  it("shows every tutorial of the style in a gallery, labelled by subtopic", async () => {
    render(<RecipeApproval versionId={5} subtopicNames={names} />);
    await userEvent.click(screen.getByRole("button", { name: /Step through the code/ }));
    await userEvent.click(screen.getByRole("button", { name: "Show tutorials" }));

    const dialog = screen.getByRole("dialog");
    expect(within(dialog).getByText("Tutorials: Step through the code")).toBeInTheDocument();
    expect(within(dialog).getByText("3 tutorials")).toBeInTheDocument();
    for (const text of ["loops worked", "lists faded", "lists worked"]) {
      expect(within(dialog).getByText(text)).toBeInTheDocument();
    }
    expect(within(dialog).getAllByText("Lists")).not.toHaveLength(0);

    await userEvent.click(within(dialog).getAllByRole("button", { name: "Retire" })[0]);
    expect(retire).toHaveBeenCalledWith(3);

    await userEvent.click(within(dialog).getByRole("button", { name: "Back" }));
    expect(within(dialog).getByRole("button", { name: "Show tutorials" })).toBeInTheDocument();
  });
});
