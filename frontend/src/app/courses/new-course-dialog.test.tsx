import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { NewCourseDialog } from "./new-course-dialog";

const createCourse = vi.fn();
const assign = vi.fn();

vi.mock("@/lib/api/queries", () => ({
  useCreateCourse: () => ({ mutateAsync: createCourse, isPending: false, error: null }),
}));

describe("NewCourseDialog", () => {
  beforeEach(() => {
    createCourse.mockReset();
    createCourse.mockResolvedValue({ id: 9 });
    assign.mockReset();
    vi.stubGlobal("location", { ...window.location, assign });
  });

  it("asks only for a name, not a subject", () => {
    render(<NewCourseDialog onOpenChange={() => {}} />);
    expect(screen.getByRole("button", { name: "Create course" })).toBeDisabled();
    expect(screen.queryByText("Subject")).not.toBeInTheDocument();
  });

  it("creates the course and lands on its assistant page", async () => {
    const user = userEvent.setup();
    render(<NewCourseDialog onOpenChange={() => {}} />);

    await user.type(screen.getByLabelText("Course name"), "CS 135");
    await user.click(screen.getByRole("button", { name: "Create course" }));

    // No subject assumed: the assistant sets it once it knows what is taught.
    expect(createCourse).toHaveBeenCalledWith({
      name: "CS 135",
      description: null,
      subject: "custom",
    });
    expect(assign).toHaveBeenCalledWith("/courses/9/assistant");
  });
});
