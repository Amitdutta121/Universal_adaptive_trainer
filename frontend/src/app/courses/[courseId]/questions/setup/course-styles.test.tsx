import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, expect, it, vi } from "vitest";
import { CourseStyles } from "./course-styles";

const { create, fetchYaml } = vi.hoisted(() => ({ create: vi.fn(), fetchYaml: vi.fn() }));
vi.mock("@/lib/api/queries", () => ({
  useCreateCourseStyle: () => ({ mutateAsync: create, isPending: false, error: null }),
  fetchStyleYaml: fetchYaml,
}));
vi.mock("../generate/use-course-question-types", () => ({
  useCourseQuestionTypes: () => ["output_prediction"],
}));

const STYLES = [
  { id: "py.trace_steps", name: "Trace a loop", question_type: "output_prediction" as const },
  { id: "py.my_output", name: "Predict my output", question_type: "output_prediction" as const },
  { id: "py.order_lines", name: "Order the lines", question_type: "parsons" as const },
];

beforeEach(() => {
  create.mockReset().mockResolvedValue({});
  fetchYaml.mockReset().mockResolvedValue("id: py.trace_steps\nname: Trace a loop\n");
});

it("starts a new style from a library style and submits its YAML", async () => {
  const user = userEvent.setup();
  render(<CourseStyles styles={STYLES} courseStyleIds={["py.my_output"]} />);
  await user.click(screen.getByText("Your course's styles (optional)"));
  await user.selectOptions(
    screen.getByRole("combobox", { name: "Start from a style" }),
    "py.trace_steps",
  );
  const editor = screen.getByRole("textbox", { name: "New style (YAML)" });
  expect(fetchYaml).toHaveBeenCalledWith("py.trace_steps");
  expect(editor).toHaveValue("id: py.trace_steps\nname: Trace a loop\n");
  await user.click(screen.getByRole("button", { name: "Check and add style" }));
  expect(create).toHaveBeenCalledWith("id: py.trace_steps\nname: Trace a loop\n");
  expect(editor).toHaveValue("");
});

it("offers only styles of the course's question types to start from", async () => {
  const user = userEvent.setup();
  render(<CourseStyles styles={STYLES} courseStyleIds={[]} />);
  await user.click(screen.getByText("Your course's styles (optional)"));
  const options = screen.getAllByRole("option").map((option) => option.textContent);
  expect(options).toEqual(["Start from a style…", "Trace a loop", "Predict my output"]);
});

it("lists only the course's own styles, each with an export", async () => {
  const user = userEvent.setup();
  render(<CourseStyles styles={STYLES} courseStyleIds={["py.my_output"]} />);
  await user.click(screen.getByText("Your course's styles (optional)"));
  expect(screen.getAllByRole("button", { name: "Export to YAML" })).toHaveLength(1);
  expect(screen.getByText("py.my_output")).toBeInTheDocument();
  expect(screen.queryByText("py.trace_steps")).not.toBeInTheDocument();
});
