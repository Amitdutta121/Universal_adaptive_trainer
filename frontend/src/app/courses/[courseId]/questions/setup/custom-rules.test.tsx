import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, expect, it, vi } from "vitest";
import { CustomRules } from "./custom-rules";

const { create, update } = vi.hoisted(() => ({ create: vi.fn(), update: vi.fn() }));
vi.mock("@/lib/api/queries", () => ({
  useCustomJudges: () => ({
    isPending: false,
    error: null,
    data: { judges: [{ id: 9, rule_text: "No global variables", kind: "llm", enabled: true }] },
  }),
  useCreateCustomJudge: () => ({ mutateAsync: create, isPending: false, error: null }),
  useUpdateCustomJudge: () => ({ mutateAsync: update, isPending: false, error: null }),
}));

beforeEach(() => {
  create.mockReset().mockResolvedValue({});
  update.mockReset().mockResolvedValue({});
});

it("saves a forbidden code rule for the current taxonomy", async () => {
  const user = userEvent.setup();
  render(<CustomRules curriculumVersionId={5} />);
  await user.click(screen.getByText("Custom rules (optional)"));
  await user.type(
    screen.getByRole("textbox", { name: "New custom rule" }),
    "No global declarations",
  );
  await user.selectOptions(screen.getByRole("combobox", { name: "Rule check" }), "pattern");
  const add = screen.getByRole("button", { name: "Add rule" });
  expect(add).toBeDisabled();
  await user.type(screen.getByRole("textbox", { name: "Forbidden pattern" }), "ast:Global");
  await user.click(add);
  expect(create).toHaveBeenCalledWith({
    curriculum_version_id: 5,
    rule_text: "No global declarations",
    kind: "pattern",
    enabled: true,
    pattern: "ast:Global",
  });
  expect(screen.getByRole("textbox", { name: "New custom rule" })).toHaveValue("");
});

it("lets the professor edit and disable an existing rule", async () => {
  const user = userEvent.setup();
  render(<CustomRules curriculumVersionId={5} />);
  await user.click(screen.getByText("Custom rules (optional)"));
  const text = screen.getByRole("textbox", { name: "Rule 9" });
  await user.clear(text);
  await user.type(text, "Use local variables only");
  await user.click(screen.getByRole("button", { name: "Disable" }));
  expect(update).toHaveBeenCalledWith({
    judgeId: 9,
    body: { rule_text: "Use local variables only", enabled: false },
  });
});
