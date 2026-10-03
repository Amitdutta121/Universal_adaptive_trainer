import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { TooltipProvider } from "@/components/ui/tooltip";
import { ApiError } from "@/lib/api/client";
import type {
  CurriculumVersionDetail,
  QuestionSetup,
  QuestionStyle,
  SaveSetupRequest,
  SetupSuggestion,
} from "@/lib/api/types";

const push = vi.fn();
vi.mock("next/navigation", async (importOriginal) => ({
  ...(await importOriginal<typeof import("next/navigation")>()),
  useParams: () => ({ courseId: "7" }),
  useRouter: () => ({ push }),
}));
vi.mock("sonner", () => ({
  toast: Object.assign(vi.fn(), { success: vi.fn(), error: vi.fn() }),
}));

const suggestMutate = vi.fn();
const saveMutate = vi.fn();
const hooks = {
  useApprovedCurriculum: vi.fn(),
  useCurrentSetup: vi.fn(),
  useSetupSuggestion: vi.fn(),
  useStyles: vi.fn(),
  useSaveSetup: vi.fn(),
};
vi.mock("@/lib/api/queries", () => ({
  useApprovedCurriculum: () => hooks.useApprovedCurriculum(),
  useCurrentSetup: (id: number | undefined) => hooks.useCurrentSetup(id),
  useSetupSuggestion: () => hooks.useSetupSuggestion(),
  useStyles: () => hooks.useStyles(),
  useSaveSetup: () => hooks.useSaveSetup(),
}));

import { QuestionSetupButton } from "./question-setup-button";

const example = (prompt: string) => ({ prompt, answer: "42", grounding: "Section 3.1", lines: [], options: [] });

const style = (id: string, name: string): QuestionStyle => ({
  id,
  subject: "intro_python",
  name,
  summary: `${name}: what the student does.`,
  question_type: "output_prediction",
  difficulty_range: ["easy", "medium"],
  checked_by: "Runs the code and compares the output",
  applies_to: [],
  examples: [example(`${name} example one`), example(`${name} example two`)],
});

const LIBRARY = [
  style("py.trace", "Predict what the code prints"),
  style("py.fill", "Fill in the missing line"),
  style("py.debug", "Find the bug"),
];

const subtopic = (id: number, name: string, position: number) => ({
  id,
  topic_id: 1,
  stable_id: null,
  name,
  description: null,
  position,
  review_status: "accepted" as const,
});

const CURRICULUM = {
  version: { id: 3, label: "Python taxonomy" },
  topics: [
    {
      id: 1,
      curriculum_version_id: 3,
      stable_id: null,
      name: "Control flow",
      description: null,
      position: 0,
      review_status: "accepted",
      subtopics: [subtopic(11, "Loops", 0), subtopic(12, "Strings", 1)],
    },
  ],
} as unknown as CurriculumVersionDetail;

const SUGGESTION: SetupSuggestion = {
  curriculum_version_id: 3,
  subject: "intro_python",
  subtopics: [
    { subtopic_id: 11, style_ids: ["py.trace"], reason: "Loops are learned by tracing iterations." },
    { subtopic_id: 12, style_ids: ["py.fill"], reason: "String methods fit fill-in-the-line." },
  ],
  cell_targets: [
    { subtopic_id: 11, difficulty: "easy", target: 2 },
    { subtopic_id: 11, difficulty: "medium", target: 3 },
    { subtopic_id: 11, difficulty: "hard", target: 1 },
    { subtopic_id: 12, difficulty: "easy", target: 2 },
    { subtopic_id: 12, difficulty: "medium", target: 2 },
    { subtopic_id: 12, difficulty: "hard", target: 2 },
  ],
};

function mockReady({
  suggestion = SUGGESTION as SetupSuggestion | undefined,
  suggestError = null as unknown,
  current = null as QuestionSetup | null,
} = {}) {
  hooks.useApprovedCurriculum.mockReturnValue({ data: CURRICULUM, isPending: false });
  hooks.useCurrentSetup.mockReturnValue({ data: { setup: current } });
  hooks.useSetupSuggestion.mockReturnValue({
    mutate: suggestMutate,
    data: suggestion,
    error: suggestError,
    isPending: false,
  });
  hooks.useStyles.mockReturnValue({ data: { subject: "intro_python", styles: LIBRARY }, error: null });
  hooks.useSaveSetup.mockReturnValue({ mutate: saveMutate, isPending: false, error: null });
}

function renderButton() {
  return render(
    <TooltipProvider>
      <QuestionSetupButton />
    </TooltipProvider>,
  );
}

async function openModal() {
  const user = userEvent.setup();
  renderButton();
  await user.click(screen.getByRole("button", { name: /set up questions/i }));
  return { user, dialog: await screen.findByRole("dialog") };
}

beforeEach(() => {
  for (const hook of Object.values(hooks)) hook.mockReset();
  suggestMutate.mockReset();
  saveMutate.mockReset();
  push.mockReset();
});

describe("QuestionSetupButton", () => {
  it("is disabled with a hint when there is no approved taxonomy", () => {
    hooks.useApprovedCurriculum.mockReturnValue({ data: undefined, isPending: false });
    hooks.useCurrentSetup.mockReturnValue({ data: undefined });
    renderButton();

    const button = screen.getByRole("button", { name: /set up questions/i });
    expect(button).toBeDisabled();
    expect(button).toHaveAccessibleDescription(/approve a taxonomy first/i);
  });

  it("reads Edit setup once a setup exists", () => {
    mockReady({
      current: {
        id: 1,
        curriculum_version_id: 3,
        approved_styles: [],
        cell_targets: [],
        created_at: "2026-10-03T10:00:00Z",
        latest_round: null,
      },
    });
    renderButton();
    expect(screen.getByRole("button", { name: /edit setup/i })).toBeEnabled();
  });
});

describe("QuestionSetupDialog", () => {
  it("asks for a suggestion on open and lists it per subtopic with the AI's reason", async () => {
    mockReady();
    const { user, dialog } = await openModal();

    expect(suggestMutate).toHaveBeenCalledTimes(1);
    expect(suggestMutate).toHaveBeenCalledWith(3);

    const loops = within(dialog).getByRole("article", { name: "Loops" });
    expect(within(loops).getByText("Predict what the code prints")).toBeInTheDocument();
    expect(within(loops).getByText(/loops are learned by tracing iterations/i)).toBeInTheDocument();
    expect(within(dialog).getByRole("article", { name: "Strings" })).toHaveTextContent(
      "Fill in the missing line",
    );

    // The two examples are behind a disclosure.
    expect(within(loops).queryByText("Predict what the code prints example one")).toBeNull();
    await user.click(within(loops).getByRole("button", { name: /examples/i }));
    expect(within(loops).getByText("Predict what the code prints example one")).toBeInTheDocument();
    expect(within(loops).getByText("Predict what the code prints example two")).toBeInTheDocument();
  });

  it("blocks Approve while a subtopic has no approved style", async () => {
    mockReady();
    const { user, dialog } = await openModal();

    const loops = within(dialog).getByRole("article", { name: "Loops" });
    const strings = within(dialog).getByRole("article", { name: "Strings" });
    await user.click(within(loops).getByRole("button", { name: /^use$/i }));
    await user.click(within(strings).getByRole("button", { name: /skip/i }));

    expect(within(dialog).getByRole("alert")).toHaveTextContent(/strings has no style/i);

    await user.click(within(dialog).getByRole("button", { name: /review targets/i }));
    expect(within(dialog).getByRole("button", { name: /approve/i })).toBeDisabled();
    expect(saveMutate).not.toHaveBeenCalled();
  });

  it("posts the approved setup and goes to the review queue", async () => {
    mockReady();
    const { user, dialog } = await openModal();

    await user.click(within(dialog).getByRole("button", { name: /use all remaining suggestions/i }));
    expect(within(dialog).queryByRole("alert")).toBeNull();

    await user.click(within(dialog).getByRole("button", { name: /review targets/i }));
    expect(within(dialog).getByTestId("setup-total")).toHaveTextContent("12");

    await user.click(within(dialog).getByRole("button", { name: /approve/i }));
    expect(saveMutate).toHaveBeenCalledTimes(1);
    const [body, options] = saveMutate.mock.calls[0] as [
      SaveSetupRequest,
      { onSuccess: (result: { setup_id: number; round_id: number }) => void },
    ];
    expect(body).toEqual({
      curriculum_version_id: 3,
      approved_styles: [
        { subtopic_id: 11, style_ids: ["py.trace"] },
        { subtopic_id: 12, style_ids: ["py.fill"] },
      ],
      cell_targets: SUGGESTION.cell_targets,
      round_size: 10,
    });

    options.onSuccess({ setup_id: 5, round_id: 9 });
    expect(push).toHaveBeenCalledWith("/courses/7/review");
  });

  it("shows a readable error when the suggestion fails", async () => {
    mockReady({
      suggestion: undefined,
      suggestError: new ApiError(
        501,
        "feature_not_available",
        "Setup suggestion is not implemented yet.",
      ),
    });
    const { dialog } = await openModal();

    expect(within(dialog).getByText(/not available yet/i)).toBeInTheDocument();
    expect(within(dialog).getByRole("button", { name: /try again/i })).toBeInTheDocument();
  });
});
