import { act, render, screen, within } from "@testing-library/react";
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
import type { QuestionVisibility } from "./setup-state";

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
const updateCourseMutate = vi.fn();
const visibilityMutate = vi.fn();
const hooks = {
  useApprovedCurriculum: vi.fn(),
  useCurrentSetup: vi.fn(),
  useSetupSuggestion: vi.fn(),
  useStyles: vi.fn(),
  useSaveSetup: vi.fn(),
  useQuestionVisibility: vi.fn(),
};
vi.mock("@/lib/api/queries", () => ({
  useApprovedCurriculum: () => hooks.useApprovedCurriculum(),
  useCurrentSetup: (id: number | undefined) => hooks.useCurrentSetup(id),
  useSetupSuggestion: (id: number, session: number) => hooks.useSetupSuggestion(id, session),
  useStyles: () => hooks.useStyles(),
  useSaveSetup: () => hooks.useSaveSetup(),
  useCourse: () => ({ data: COURSE, error: null, refetch: vi.fn() }),
  useUpdateCourse: () => ({ mutate: updateCourseMutate, isPending: false, error: null }),
  useQuestionVisibility: (courseId: number, versionId: number | null) =>
    hooks.useQuestionVisibility(courseId, versionId),
  useSetQuestionVisibility: () => ({ mutate: visibilityMutate, isPending: false, error: null }),
  useCustomJudges: () => ({ data: { judges: [] }, isPending: false, error: null }),
  useCreateCustomJudge: () => ({ error: null, isPending: false }),
  useUpdateCustomJudge: () => ({ error: null, isPending: false }),
  useCreateCourseStyle: () => ({ error: null, isPending: false }),
  fetchStyleYaml: () => Promise.resolve(""),
}));

vi.mock("../generate/use-course-question-types", () => ({
  useCourseQuestionTypes: () => [],
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

// Library order differs from type order on purpose: the modal lists types in registry order.
const LIBRARY = [
  style("py.trace", "Predict what the code prints", "output_prediction", ["easy", "medium"]),
  style("py.fill", "Fill in the missing line", "code_completion", ["medium", "hard"]),
  style("py.debug", "Find the bug", "debugging", ["medium"]),
  style("py.concept", "Check one concept", "multiple_choice", ["easy"]),
  style("py.write", "Write a small function", "coding", ["hard"]),
];

/** The course allows every type in the library but coding. */
const COURSE = {
  id: 7,
  name: "Intro Python",
  question_types: ["multiple_choice", "output_prediction", "code_completion", "debugging"],
};

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

const NO_QUESTIONS: QuestionVisibility = { by_style: [], by_type: [], by_cell: [] };

function mockReady({
  suggestion = SUGGESTION as SetupSuggestion | undefined,
  suggestError = null as unknown,
  current = null as QuestionSetup | null,
  visibility = NO_QUESTIONS as QuestionVisibility,
} = {}) {
  hooks.useQuestionVisibility.mockReturnValue({ data: visibility, error: null, refetch: vi.fn() });
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
  updateCourseMutate.mockReset();
  visibilityMutate.mockReset();
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
  type User = ReturnType<typeof userEvent.setup>;
  const typeList = (dialog: HTMLElement) =>
    within(dialog).getByRole("navigation", { name: /question types/i });
  const scopeRail = (dialog: HTMLElement) =>
    within(dialog).getByRole("navigation", { name: /scope/i });
  const railButton = (dialog: HTMLElement, name: RegExp) =>
    within(scopeRail(dialog)).getByRole("button", { name });
  const styleSwitch = (dialog: HTMLElement, name: string) =>
    within(dialog).getByRole("switch", { name: `Use ${name}` });
  const pickType = (user: User, dialog: HTMLElement, label: string) =>
    user.click(within(typeList(dialog)).getByRole("button", { name: new RegExp(`^${label}`) }));
  const pickSubtopic = (user: User, dialog: HTMLElement, name: string) =>
    user.click(railButton(dialog, new RegExp(`^${name}`)));

  it("opens on the whole course with the library's types in registry order", async () => {
    mockReady();
    const { dialog } = await openModal();

    expect(hooks.useSetupSuggestion).toHaveBeenCalledWith(3, 1);
    expect(railButton(dialog, /whole course/i)).toHaveAttribute("aria-current", "true");
    expect(
      within(typeList(dialog))
        .getAllByRole("switch")
        .map((toggle) => toggle.getAttribute("aria-label")),
    ).toEqual([
      "Use Multiple choice",
      "Use Output prediction",
      "Use Code completion",
      "Use Debugging",
      "Use Coding",
    ]);
    // Every style of an allowed type starts on for the course.
    expect(styleSwitch(dialog, "Multiple choice")).toBeChecked();
    expect(within(dialog).getByText("4 styles on")).toBeInTheDocument();
  });

  it("greys a type the course does not allow and allows it from here", async () => {
    mockReady();
    const { user, dialog } = await openModal();

    expect(styleSwitch(dialog, "Coding")).toBeDisabled();
    expect(within(typeList(dialog)).getByText("Not allowed in this course")).toBeInTheDocument();
    await pickType(user, dialog, "Coding");
    const detail = within(dialog).getByRole("region", { name: "Coding" });
    expect(within(detail).getByText("Not allowed in this course.")).toBeInTheDocument();
    expect(styleSwitch(dialog, "Write a small function")).toBeDisabled();

    await user.click(within(detail).getByRole("button", { name: /allow for this course/i }));
    expect(updateCourseMutate).toHaveBeenCalledTimes(1);
    const [variables, options] = updateCourseMutate.mock.calls[0] as [
      { courseId: number; body: { question_types: string[] } },
      { onSuccess: () => void },
    ];
    expect(variables.courseId).toBe(7);
    expect([...variables.body.question_types].sort()).toEqual(
      [...COURSE.question_types, "coding"].sort(),
    );

    act(() => options.onSuccess());
    expect(styleSwitch(dialog, "Write a small function")).toBeEnabled();
    expect(styleSwitch(dialog, "Write a small function")).toBeChecked();
    expect(within(detail).queryByText("Not allowed in this course.")).toBeNull();
  });

  it("turns a type off for the course and every subtopic follows", async () => {
    mockReady();
    const { user, dialog } = await openModal();
    expect(within(dialog).queryByRole("alert")).toBeNull();

    await user.click(styleSwitch(dialog, "Output prediction"));
    expect(within(dialog).getByRole("alert")).toHaveTextContent(/loops has no style/i);

    await pickSubtopic(user, dialog, "Loops");
    await pickType(user, dialog, "Output prediction");
    const row = within(dialog).getByRole("listitem", { name: "Predict what the code prints" });
    expect(within(row).getByText("Off for the course")).toBeInTheDocument();
    expect(styleSwitch(dialog, "Predict what the code prints")).toBeDisabled();
  });

  it("keeps a subtopic edit local, marks it Custom and resets it", async () => {
    mockReady();
    const { user, dialog } = await openModal();

    await pickSubtopic(user, dialog, "Loops");
    expect(within(dialog).getByRole("region", { name: "Loops" })).toHaveTextContent(
      /follows the course/i,
    );

    await pickType(user, dialog, "Output prediction");
    const trace = within(dialog).getByRole("listitem", { name: "Predict what the code prints" });
    expect(within(trace).getByText("Suggested")).toBeInTheDocument();
    expect(styleSwitch(dialog, "Predict what the code prints")).toBeChecked();

    await pickType(user, dialog, "Debugging");
    await user.click(styleSwitch(dialog, "Find the bug"));
    expect(styleSwitch(dialog, "Find the bug")).toBeChecked();
    expect(railButton(dialog, /^loops/i)).toHaveTextContent("Custom");

    // Strings is untouched.
    await pickSubtopic(user, dialog, "Strings");
    expect(styleSwitch(dialog, "Find the bug")).not.toBeChecked();

    await pickSubtopic(user, dialog, "Loops");
    await user.click(within(dialog).getByRole("button", { name: /reset to course/i }));
    expect(styleSwitch(dialog, "Find the bug")).not.toBeChecked();
    expect(railButton(dialog, /^loops/i)).not.toHaveTextContent("Custom");
  });

  it("flags a planned difficulty no style covers, in step 2 and in the targets", async () => {
    mockReady();
    const { user, dialog } = await openModal();

    await pickSubtopic(user, dialog, "Loops");
    const coverage = within(dialog).getByRole("list", { name: /difficulty coverage/i });
    const hard = within(coverage).getByText("Hard").closest("li") as HTMLElement;
    expect(hard).toHaveTextContent(/1 planned · no style on/i);

    await user.click(within(dialog).getByRole("button", { name: /review targets/i }));
    const loopsRow = within(dialog).getByRole("button", { name: "Loops" }).closest("tr");
    expect(loopsRow).toHaveTextContent(/1 · no style/);

    // The subtopic name jumps back to step 2 scoped to it.
    await user.click(within(dialog).getByRole("button", { name: "Loops" }));
    expect(within(dialog).getByRole("region", { name: "Loops" })).toBeInTheDocument();
    expect(railButton(dialog, /^loops/i)).toHaveAttribute("aria-current", "true");
  });

  it("blocks Approve while a subtopic has no style", async () => {
    mockReady();
    const { user, dialog } = await openModal();

    await pickSubtopic(user, dialog, "Loops");
    await pickType(user, dialog, "Output prediction");
    await user.click(styleSwitch(dialog, "Predict what the code prints"));
    expect(within(dialog).getByRole("alert")).toHaveTextContent(/loops has no style/i);

    await user.click(within(dialog).getByRole("button", { name: /review targets/i }));
    expect(within(dialog).getByRole("button", { name: "Loops" }).closest("tr")).toHaveTextContent(
      "Custom",
    );
    expect(within(dialog).getByRole("button", { name: /approve/i })).toBeDisabled();
    expect(saveMutate).not.toHaveBeenCalled();
  });

  it("posts approved_styles and goes to the review queue", async () => {
    mockReady();
    const { user, dialog } = await openModal();

    await pickSubtopic(user, dialog, "Loops");
    await pickType(user, dialog, "Debugging");
    await user.click(styleSwitch(dialog, "Find the bug"));

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

  it("opens an existing setup on what it saved, without asking the AI", async () => {
    const current: QuestionSetup = {
      id: 1,
      curriculum_version_id: 3,
      approved_styles: [
        { subtopic_id: 11, style_ids: ["py.trace", "py.concept"] },
        { subtopic_id: 12, style_ids: ["py.fill"] },
      ],
      // Not the suggestion's counts: editing keeps the saved ones.
      cell_targets: [
        { subtopic_id: 11, difficulty: "easy", target: 5 },
        { subtopic_id: 12, difficulty: "medium", target: 4 },
      ],
      created_at: "2026-10-03T10:00:00Z",
      latest_round: null,
    };
    mockReady({ current });
    const user = userEvent.setup();
    renderButton();
    await user.click(screen.getByRole("button", { name: /edit setup/i }));
    const dialog = await screen.findByRole("dialog");

    // Session 0 keeps the suggestion query disabled: no AI call.
    for (const [, session] of hooks.useSetupSuggestion.mock.calls) expect(session).toBe(0);
    // Debugging was used nowhere, so it is off for the course.
    expect(styleSwitch(dialog, "Debugging")).not.toBeChecked();
    // Nothing is a local edit on opening, and no AI reasons or Suggested badges show.
    expect(railButton(dialog, /^loops/i)).not.toHaveTextContent("Custom");
    expect(railButton(dialog, /^strings/i)).not.toHaveTextContent("Custom");
    expect(within(dialog).queryByText(/why the ai suggested/i)).toBeNull();

    await user.click(within(dialog).getByRole("button", { name: /review targets/i }));
    expect(within(dialog).getByText(/target: 9 approved questions/i)).toBeInTheDocument();
    await user.click(within(dialog).getByRole("button", { name: /approve/i }));
    const [body] = saveMutate.mock.calls[0] as [SaveSetupRequest];
    expect(body.approved_styles).toEqual(current.approved_styles);
    expect(body.cell_targets).toEqual(current.cell_targets);
  });

  it("asks the AI when there is no setup yet", async () => {
    mockReady();
    await openModal();
    const sessions = hooks.useSetupSuggestion.mock.calls.map(([, session]) => session);
    expect(sessions.some((session) => session > 0)).toBe(true);
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

describe("Turning a style off or on with existing questions (ADR-070)", () => {
  const typeSwitch = (dialog: HTMLElement, label: string) =>
    within(within(dialog).getByRole("navigation", { name: /question types/i })).getByRole(
      "switch",
      { name: `Use ${label}` },
    );
  const confirmDialog = (name: RegExp) => screen.findByRole("dialog", { name });

  /** Five approved py.trace questions: two at Loops/easy (target 2), one at Loops/medium. */
  const APPROVED: QuestionVisibility = {
    by_style: [{ style_id: "py.trace", approved: 5, hidden: 0 }],
    by_type: [{ question_type: "output_prediction", approved: 5, hidden: 0 }],
    by_cell: [
      { subtopic_id: 11, style_id: "py.trace", difficulty: "easy", approved: 2, hidden: 0 },
      { subtopic_id: 11, style_id: "py.trace", difficulty: "medium", approved: 1, hidden: 0 },
    ],
  };

  it("asks before turning a type off for the course, and hides on request", async () => {
    mockReady({ visibility: APPROVED });
    const { user, dialog } = await openModal();

    await user.click(typeSwitch(dialog, "Output prediction"));
    const ask = await confirmDialog(/turn off “output prediction”/i);
    expect(ask).toHaveTextContent("For the whole course · 5 approved questions");
    expect(within(ask).getByRole("radio", { name: /stop new questions/i })).toBeChecked();

    await user.click(
      within(ask).getByRole("radio", { name: /also hide the 5 existing questions from students/i }),
    );
    expect(ask).toHaveTextContent("1 subtopic level falls below target");
    await user.click(within(ask).getByRole("button", { name: "Turn off" }));

    expect(visibilityMutate).toHaveBeenCalledWith(
      { hidden: true, style_ids: ["py.trace"], subtopic_id: null },
      expect.anything(),
    );
    expect(typeSwitch(dialog, "Output prediction")).not.toBeChecked();
  });

  it("counts a subtopic's own questions and keeps them when asked to", async () => {
    mockReady({ visibility: APPROVED });
    const { user, dialog } = await openModal();

    await user.click(
      within(within(dialog).getByRole("navigation", { name: /scope/i })).getByRole("button", {
        name: /^Loops/,
      }),
    );
    await user.click(
      within(within(dialog).getByRole("navigation", { name: /question types/i })).getByRole(
        "button",
        { name: /^Output prediction/ },
      ),
    );
    await user.click(
      within(dialog).getByRole("switch", { name: "Use Predict what the code prints" }),
    );
    const ask = await confirmDialog(/turn off “predict what the code prints”/i);
    expect(ask).toHaveTextContent("For Loops · 3 approved questions");
    await user.click(within(ask).getByRole("button", { name: "Turn off" }));

    expect(visibilityMutate).not.toHaveBeenCalled();
    expect(
      within(dialog).getByRole("switch", { name: "Use Predict what the code prints" }),
    ).not.toBeChecked();
  });

  it("leaves the switch on when the question is cancelled", async () => {
    mockReady({ visibility: APPROVED });
    const { user, dialog } = await openModal();

    await user.click(typeSwitch(dialog, "Output prediction"));
    const ask = await confirmDialog(/turn off/i);
    await user.click(within(ask).getByRole("button", { name: "Cancel" }));

    expect(typeSwitch(dialog, "Output prediction")).toBeChecked();
    expect(visibilityMutate).not.toHaveBeenCalled();
  });

  it("offers to show hidden questions again when a style is turned back on", async () => {
    mockReady({
      visibility: {
        by_style: [{ style_id: "py.trace", approved: 0, hidden: 4 }],
        by_type: [{ question_type: "output_prediction", approved: 0, hidden: 4 }],
        by_cell: [],
      },
    });
    const { user, dialog } = await openModal();

    // Nothing approved behind it: off without asking.
    await user.click(typeSwitch(dialog, "Output prediction"));
    expect(screen.getAllByRole("dialog")).toHaveLength(1);
    expect(typeSwitch(dialog, "Output prediction")).not.toBeChecked();

    await user.click(typeSwitch(dialog, "Output prediction"));
    const ask = await confirmDialog(/turn on “output prediction”/i);
    expect(ask).toHaveTextContent("For the whole course · 4 hidden questions");
    expect(
      within(ask).getByRole("radio", { name: /show the 4 hidden questions to students again/i }),
    ).toBeChecked();
    await user.click(within(ask).getByRole("button", { name: "Turn on" }));

    expect(visibilityMutate).toHaveBeenCalledWith(
      { hidden: false, style_ids: ["py.trace"], subtopic_id: null },
      expect.anything(),
    );
    expect(typeSwitch(dialog, "Output prediction")).toBeChecked();
  });

  it("does not ask when no questions are behind the switch", async () => {
    mockReady();
    const { user, dialog } = await openModal();

    await user.click(typeSwitch(dialog, "Output prediction"));
    expect(screen.getAllByRole("dialog")).toHaveLength(1);
    expect(typeSwitch(dialog, "Output prediction")).not.toBeChecked();
  });
});
