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
  useSetupSuggestion: (id: number, session: number) => hooks.useSetupSuggestion(id, session),
  useStyles: () => hooks.useStyles(),
  useSaveSetup: () => hooks.useSaveSetup(),
  useCustomJudges: () => ({ data: { judges: [] }, isPending: false, error: null }),
  useCreateCustomJudge: () => ({ error: null, isPending: false }),
  useUpdateCustomJudge: () => ({ error: null, isPending: false }),
}));

import { QuestionSetupButton } from "./question-setup-button";

const example = (prompt: string) => ({
  prompt,
  answer: "42",
  grounding: "Section 3.1",
  lines: [],
  options: [],
});

const style = (
  id: string,
  name: string,
  question_type: QuestionStyle["question_type"],
  difficulty_range: QuestionStyle["difficulty_range"],
): QuestionStyle => ({
  id,
  subject: "intro_python",
  name,
  summary: `${name}: what the student does.`,
  question_type,
  difficulty_range,
  checked_by: "Runs the code and compares the output",
  applies_to: [],
  examples: [example(`${name} example one`), example(`${name} example two`)],
});

// Library order differs from group order on purpose: the modal regroups it.
const LIBRARY = [
  style("py.trace", "Predict what the code prints", "output_prediction", ["easy", "medium"]),
  style("py.fill", "Fill in the missing line", "code_completion", ["medium", "hard"]),
  style("py.debug", "Find the bug", "debugging", ["medium"]),
  style("py.concept", "Check one concept", "multiple_choice", ["easy"]),
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
    {
      subtopic_id: 11,
      style_ids: ["py.trace"],
      reason: "Loops are learned by tracing iterations.",
    },
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
    data: suggestion,
    error: suggestError,
    isPending: !suggestion && !suggestError,
    refetch: vi.fn(),
  });
  hooks.useStyles.mockReturnValue({
    data: { subject: "intro_python", styles: LIBRARY },
    error: null,
  });
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
  /** The library's styles in one subtopic, in on-screen order (the Suggested mark aside). */
  const styleToggles = (scope: HTMLElement) =>
    within(scope)
      .getAllByRole("button", { pressed: true })
      .concat(within(scope).getAllByRole("button", { pressed: false }))
      .sort((a, b) => (a.compareDocumentPosition(b) & Node.DOCUMENT_POSITION_FOLLOWING ? -1 : 1))
      .map((button) => button.textContent?.replace("Suggested", ""));

  it("asks for a suggestion on open and starts with the AI's picks selected", async () => {
    mockReady();
    const { user, dialog } = await openModal();

    expect(hooks.useSetupSuggestion).toHaveBeenCalledWith(3, 1);

    const loops = within(dialog).getByRole("region", { name: "Loops" });
    expect(
      within(loops).getByRole("button", { name: /^predict what the code prints/i }),
    ).toHaveAttribute("aria-pressed", "true");
    expect(
      within(loops).getByRole("button", { name: /^predict what the code prints/i }),
    ).toHaveTextContent(/suggested/i);
    expect(
      within(loops).getByRole("button", { name: /^fill in the missing line/i }),
    ).toHaveAttribute("aria-pressed", "false");

    // The AI's reason and the two examples are one click away.
    expect(within(loops).queryByText(/loops are learned by tracing iterations/i)).toBeNull();
    await user.click(within(loops).getByRole("button", { name: /why the ai suggested these/i }));
    expect(within(loops).getByText(/loops are learned by tracing iterations/i)).toBeInTheDocument();

    expect(within(loops).queryByText("Predict what the code prints example one")).toBeNull();
    await user.click(
      within(loops).getByRole("button", { name: /examples for predict what the code prints/i }),
    );
    expect(within(loops).getByText("Predict what the code prints example one")).toBeInTheDocument();
    expect(within(loops).getByText("Predict what the code prints example two")).toBeInTheDocument();
  });

  it("groups the library by what the student does, the same way for every subtopic", async () => {
    mockReady();
    const { user, dialog } = await openModal();

    const loops = within(dialog).getByRole("region", { name: "Loops" });
    expect(
      within(loops)
        .getAllByRole("region")
        .map((group) => group.getAttribute("aria-label")),
    ).toEqual(["Concept questions", "Code tracing", "Code completion", "Debugging"]);
    const loopsOrder = styleToggles(loops);

    const rail = within(dialog).getByRole("navigation", { name: /subtopics/i });
    await user.click(within(rail).getByRole("button", { name: /strings/i }));

    const strings = within(dialog).getByRole("region", { name: "Strings" });
    expect(styleToggles(strings)).toEqual(loopsOrder);
    expect(
      within(strings).getByRole("button", { name: /^fill in the missing line/i }),
    ).toHaveAttribute("aria-pressed", "true");
    expect(
      within(strings).getByRole("button", { name: /^predict what the code prints/i }),
    ).toHaveAttribute("aria-pressed", "false");
  });

  it("flags a difficulty that no selected style can be written at", async () => {
    mockReady();
    const { user, dialog } = await openModal();

    const loops = within(dialog).getByRole("region", { name: "Loops" });
    const coverage = within(loops).getByRole("list", { name: /questions planned per difficulty/i });
    const hard = within(coverage).getByText("Hard").closest("li") as HTMLElement;
    expect(hard).toHaveTextContent(/1 question planned · no selected style writes these/i);

    await user.click(within(loops).getByRole("button", { name: /^fill in the missing line/i }));
    expect(hard).toHaveTextContent(/1 selected style writes these/i);
  });

  it("blocks Approve while a subtopic has no selected style", async () => {
    mockReady();
    const { user, dialog } = await openModal();

    const loops = within(dialog).getByRole("region", { name: "Loops" });
    await user.click(within(loops).getByRole("button", { name: /^predict what the code prints/i }));

    expect(within(dialog).getByRole("alert")).toHaveTextContent(/loops has no style/i);

    await user.click(within(dialog).getByRole("button", { name: /review targets/i }));
    expect(within(dialog).getByRole("button", { name: /approve/i })).toBeDisabled();
    expect(saveMutate).not.toHaveBeenCalled();
  });

  it("posts the approved setup and goes to the review queue", async () => {
    mockReady();
    const { user, dialog } = await openModal();
    expect(within(dialog).queryByRole("alert")).toBeNull();

    // Add a library style the AI did not suggest.
    const loops = within(dialog).getByRole("region", { name: "Loops" });
    await user.click(within(loops).getByRole("button", { name: /^find the bug/i }));

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
        { subtopic_id: 11, style_ids: ["py.trace", "py.debug"] },
        { subtopic_id: 12, style_ids: ["py.fill"] },
      ],
      cell_targets: SUGGESTION.cell_targets,
      round_size: 10,
    });

    options.onSuccess({ setup_id: 5, round_id: 9 });
    expect(push).toHaveBeenCalledWith("/courses/7/review");
  });

  it("never preselects a suggested style the library no longer has", async () => {
    mockReady({
      suggestion: {
        ...SUGGESTION,
        subtopics: [
          { subtopic_id: 11, style_ids: ["py.trace", "py.retired"], reason: "Tracing." },
          SUGGESTION.subtopics[1],
        ],
      },
    });
    const { user, dialog } = await openModal();

    expect(
      within(dialog).getByText(/1 suggested style is no longer in the library/i),
    ).toBeVisible();
    await user.click(within(dialog).getByRole("button", { name: /review targets/i }));
    await user.click(within(dialog).getByRole("button", { name: /approve/i }));
    const [body] = saveMutate.mock.calls[0] as [SaveSetupRequest];
    expect(body.approved_styles[0]).toEqual({ subtopic_id: 11, style_ids: ["py.trace"] });
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
