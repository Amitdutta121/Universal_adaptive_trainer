import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import { ApprovalCardView, describeCall, findCall } from "./approval-card";

const CURRICULUM = {
  name: "approve_curriculum",
  args: {
    document: {
      schema_version: "1",
      label: "Intro Python",
      topics: [
        { name: "Loops", subtopics: [{ name: "for" }, { name: "while" }] },
        { name: "Functions", subtopics: [{ name: "Defining" }] },
      ],
    },
  },
};

describe("ApprovalCardView", () => {
  it("shows what approving does and resumes with approved: true on Approve", () => {
    const onDecide = vi.fn();
    render(<ApprovalCardView call={CURRICULUM} onDecide={onDecide} />);

    expect(screen.getByText('Save the curriculum "Intro Python"')).toBeInTheDocument();
    expect(screen.getByText("Loops (2 subtopics)")).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: /approve/i }));

    expect(onDecide).toHaveBeenCalledExactlyOnceWith(true);
    expect(screen.getByText("Approved")).toBeInTheDocument();
    expect(screen.queryByRole("button")).not.toBeInTheDocument();
  });

  it("rejects without approving", () => {
    const onDecide = vi.fn();
    render(<ApprovalCardView call={CURRICULUM} onDecide={onDecide} />);
    fireEvent.click(screen.getByRole("button", { name: /reject/i }));
    expect(onDecide).toHaveBeenCalledExactlyOnceWith(false);
    expect(screen.getByText("Rejected")).toBeInTheDocument();
  });
});

describe("describeCall", () => {
  it("states the call count a generation run was priced at", () => {
    const { title, lines } = describeCall({
      name: "run_generation",
      args: { plan_id: "x", model_calls: 42 },
    });
    expect(title).toBe("Start generating questions");
    expect(lines[0]).toContain("42 model calls");
  });

  it("names a style from its YAML", () => {
    const { title } = describeCall({
      name: "save_style",
      args: { yaml: "id: py.my_output\nname: Predict my output\n" },
    });
    expect(title).toBe('Add the style "Predict my output"');
  });

  it("names the curriculum version a publish freezes", () => {
    const { lines } = describeCall({ name: "publish_set", args: { curriculum_version_id: 7 } });
    expect(lines[0]).toContain("curriculum version 7");
  });
});

describe("findCall", () => {
  it("finds the interrupted call's name and arguments in the chat messages", () => {
    const messages = [
      { role: "user" },
      {
        role: "assistant",
        toolCalls: [
          {
            id: "call-1",
            function: { name: "publish_set", arguments: '{"curriculum_version_id":3}' },
          },
        ],
      },
    ];
    const interrupt = { id: "pyd_ai_call-1", reason: "tool_call", toolCallId: "call-1" };
    expect(findCall(messages, interrupt)).toEqual({
      name: "publish_set",
      args: { curriculum_version_id: 3 },
    });
    expect(findCall(messages, { ...interrupt, toolCallId: "other" })).toBeNull();
  });
});
