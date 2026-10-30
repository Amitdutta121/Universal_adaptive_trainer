import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { NewCourseDialog } from "./new-course-dialog";

const createCourse = vi.fn();

vi.mock("@/lib/api/queries", () => ({
  useAssessmentCatalog: () => ({
    isPending: false,
    isError: false,
    data: {
      question_types: [
        { id: "multiple_choice", label: "Multiple choice" },
        { id: "coding", label: "Write code" },
      ],
      subjects: [
        {
          id: "intro_python",
          label: "Intro programming (Python)",
          default_types: ["multiple_choice", "coding"],
          ready: true,
        },
        { id: "physics", label: "Physics", default_types: ["multiple_choice"], ready: false },
      ],
    },
  }),
  useCreateCourse: () => ({ mutateAsync: createCourse, isPending: false, error: null }),
}));

describe("NewCourseDialog", () => {
  beforeEach(() => {
    createCourse.mockReset();
    createCourse.mockResolvedValue({ id: 9 });
    vi.stubGlobal("location", { ...window.location, assign: vi.fn() });
  });

  it("offers a subject without question styles as coming soon, not as a choice", () => {
    render(<NewCourseDialog onOpenChange={() => {}} />);
    const physics = screen.getByRole("button", { name: /Physics/ });
    expect(physics).toBeDisabled();
    expect(screen.getByText("Coming soon")).toBeInTheDocument();
  });

  it("creates the course in one step with the subject's default question types", async () => {
    const user = userEvent.setup();
    render(<NewCourseDialog onOpenChange={() => {}} />);
    const create = screen.getByRole("button", { name: "Create course" });
    expect(create).toBeDisabled();

    await user.type(screen.getByLabelText("Course name"), "CS 135");
    await user.click(screen.getByRole("button", { name: /Intro programming/ }));
    await user.click(create);

    // No question_types: the server stores the subject's defaults.
    expect(createCourse).toHaveBeenCalledWith({
      name: "CS 135",
      description: null,
      subject: "intro_python",
    });
  });
});
