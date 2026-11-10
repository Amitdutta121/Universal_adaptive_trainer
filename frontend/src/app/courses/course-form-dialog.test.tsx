import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";
import type { Schemas } from "@/lib/api/types";

const updateCourse = vi.fn();
const setVisibility = vi.fn();
const visibility = vi.fn();

const qtype = (id: string, label: string) => ({
  id,
  label,
  group: "core",
  offerable: true,
  ai_graded: false,
  widget: "a choice",
  graded_by: [],
  also_needs: [],
});

const CATALOG = {
  groups: [{ id: "core", title: "Core", hint: "" }],
  capabilities: [],
  question_types: [qtype("multiple_choice", "Multiple choice"), qtype("coding", "Write code")],
  subjects: [
    {
      id: "intro_python",
      label: "Intro programming (Python)",
      default_types: ["multiple_choice", "coding"],
      coming_soon_types: [],
      primary_groups: ["core"],
      examples: {},
      ready: true,
    },
  ],
};

vi.mock("@/lib/api/queries", () => ({
  useAssessmentCatalog: () => ({ isError: false, data: CATALOG }),
  useUpdateCourse: () => ({ mutateAsync: updateCourse, isPending: false, error: null }),
  useQuestionVisibility: (courseId: number, versionId: number | null) =>
    visibility(courseId, versionId),
  useSetQuestionVisibility: () => ({ mutateAsync: setVisibility, isPending: false, error: null }),
}));

import { CourseFormDialog } from "./courses-screen";

const COURSE = {
  id: 2,
  name: "CS115",
  description: null,
  subject: "intro_python",
  question_types: ["multiple_choice", "coding"],
  figures_enabled: true,
} as unknown as Schemas["CourseOut"];

function counts(approved: number, hidden: number) {
  return {
    data: {
      by_style: [],
      by_cell: [],
      by_type: [{ question_type: "coding", approved, hidden }],
    },
  };
}

describe("CourseFormDialog: disallowing a type with questions (ADR-070)", () => {
  beforeEach(() => {
    updateCourse.mockReset().mockResolvedValue({});
    setVisibility.mockReset().mockResolvedValue({ changed: 3 });
    visibility.mockReset();
  });

  it("offers to hide the type's approved questions and hides them after saving", async () => {
    visibility.mockReturnValue(counts(3, 0));
    const onOpenChange = vi.fn();
    const user = userEvent.setup();
    render(<CourseFormDialog course={COURSE} onOpenChange={onOpenChange} />);
    expect(visibility).toHaveBeenCalledWith(2, null);

    await user.click(screen.getByRole("checkbox", { name: /write code/i }));
    const ask = await screen.findByRole("dialog", { name: /turn off “write code”/i });
    expect(ask).toHaveTextContent("For the whole course · 3 approved questions");
    await user.click(within(ask).getByRole("radio", { name: /also hide the 3 existing/i }));
    await user.click(within(ask).getByRole("button", { name: "Turn off" }));

    expect(screen.getByRole("checkbox", { name: /write code/i })).not.toBeChecked();
    expect(setVisibility).not.toHaveBeenCalled(); // only once the course saves
    await user.click(screen.getByRole("button", { name: "Save changes" }));

    expect(updateCourse).toHaveBeenCalledWith({
      courseId: 2,
      body: { name: "CS115", description: "", question_types: ["multiple_choice"] },
    });
    expect(setVisibility).toHaveBeenCalledWith({ hidden: true, question_types: ["coding"] });
    expect(onOpenChange).toHaveBeenCalledWith(false);
  });

  it("keeps the questions when the professor only stops new ones", async () => {
    visibility.mockReturnValue(counts(3, 0));
    const user = userEvent.setup();
    render(<CourseFormDialog course={COURSE} onOpenChange={() => {}} />);

    await user.click(screen.getByRole("checkbox", { name: /write code/i }));
    const ask = await screen.findByRole("dialog", { name: /turn off/i });
    await user.click(within(ask).getByRole("button", { name: "Turn off" }));
    await user.click(screen.getByRole("button", { name: "Save changes" }));

    expect(updateCourse).toHaveBeenCalledTimes(1);
    expect(setVisibility).not.toHaveBeenCalled();
  });

  it("offers to show hidden questions when a type is allowed again", async () => {
    visibility.mockReturnValue(counts(0, 2));
    const user = userEvent.setup();
    render(
      <CourseFormDialog
        course={{ ...COURSE, question_types: ["multiple_choice"] }}
        onOpenChange={() => {}}
      />,
    );

    await user.click(screen.getByRole("checkbox", { name: /write code/i }));
    const ask = await screen.findByRole("dialog", { name: /turn on “write code”/i });
    expect(ask).toHaveTextContent("2 hidden questions");
    await user.click(within(ask).getByRole("button", { name: "Turn on" }));
    await user.click(screen.getByRole("button", { name: "Save changes" }));

    expect(setVisibility).toHaveBeenCalledWith({ hidden: false, question_types: ["coding"] });
  });

  it("does not ask for a type without questions", async () => {
    visibility.mockReturnValue(counts(0, 0));
    const user = userEvent.setup();
    render(<CourseFormDialog course={COURSE} onOpenChange={() => {}} />);

    await user.click(screen.getByRole("checkbox", { name: /write code/i }));
    expect(screen.getAllByRole("dialog")).toHaveLength(1);
    expect(screen.getByRole("checkbox", { name: /write code/i })).not.toBeChecked();
  });

  it("turns figures off for the course", async () => {
    visibility.mockReturnValue(counts(0, 0));
    const user = userEvent.setup();
    render(<CourseFormDialog course={COURSE} onOpenChange={() => {}} />);

    const figures = screen.getByRole("checkbox", { name: /allow figure questions/i });
    expect(figures).toBeChecked();
    await user.click(figures);
    expect(figures).not.toBeChecked();
    await user.click(screen.getByRole("button", { name: "Save changes" }));

    expect(updateCourse).toHaveBeenCalledWith({
      courseId: 2,
      body: { name: "CS115", description: "", figures_enabled: false },
    });
  });
});
