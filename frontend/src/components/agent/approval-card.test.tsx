import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import { ApprovalCardView, describeCall, findCall } from "./approval-card";

// Flat, as the model sends it: Pydantic AI uses a lone model parameter's fields as the tool's
// arguments, so `approve_curriculum(document)` gets no `document` key.
const CURRICULUM = {
  name: "approve_curriculum",
  args: {
    schema_version: "1",
    label: "Intro Python",
    topics: [
      { name: "Loops", subtopics: [{ name: "for" }, { name: "while" }] },
      { name: "Functions", subtopics: [{ name: "Defining" }] },
    ],
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

  it("names a recipe from its YAML and says students wait for approval", () => {
    const { title, lines } = describeCall({
      name: "save_recipe",
      args: { yaml: "id: exp.analogy\nname: Everyday analogy\n" },
    });
    expect(title).toBe('Save the recipe "Everyday analogy"');
    expect(lines.join(" ")).toContain("only once it is approved");
  });

  it("tells approving a recipe from stopping it", () => {
    const args = { recipe_id: "exp.analogy", curriculum_version_id: 9 };
    expect(describeCall({ name: "decide_recipe", args: { ...args, approved: true } }).title).toBe(
      "Approve the recipe exp.analogy for students",
    );
    expect(describeCall({ name: "decide_recipe", args: { ...args, approved: false } }).title).toBe(
      "Stop using the recipe exp.analogy",
    );
  });

  it("shows the link a YouTube import would fetch", () => {
    const { title, lines } = describeCall({
      name: "import_material",
      args: { url: "https://youtu.be/AbCdEfGhIjK" },
    });
    expect(title).toBe("Import a YouTube video");
    expect(lines[0]).toBe("https://youtu.be/AbCdEfGhIjK");
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

  it("shows the proposed design an approve_course_design call saves", () => {
    const design = {
      design_id: "d1",
      title: "AI in Games",
      topic_count: 2,
      subtopic_count: 5,
      styles: [
        { name: "Trace A* by hand", new: true },
        { name: "Pick the right search", new: false },
      ],
      recipes: [{ name: "State machine diagram", new: true }],
    };
    const messages = [
      { role: "tool", content: JSON.stringify(design) },
      {
        role: "assistant",
        toolCalls: [
          {
            id: "call-2",
            function: { name: "approve_course_design", arguments: '{"design_id":"d1"}' },
          },
        ],
      },
    ];
    const call = findCall(messages, { id: "i", reason: "tool_call", toolCallId: "call-2" });
    expect(call?.args.design).toEqual(design);
    const { title, lines } = describeCall(call as NonNullable<typeof call>);
    expect(title).toBe('Save the course design "AI in Games"');
    expect(lines).toContain("New question style: Trace A* by hand (you review its examples next)");
    expect(lines).toContain("New tutorial recipe: State machine diagram");
    expect(lines.join(" ")).not.toContain("Pick the right search");
    expect(lines.join(" ")).toContain("about 2 model calls");
  });

  it("shows a drafted style's examples on its save_style card", () => {
    const style = {
      id: "ai.trace_astar",
      name: "Trace A* by hand",
      summary: "Give the order A* expands nodes.",
      question_type: "multiple_choice",
      difficulty_range: ["medium"],
      checked_by: "the answer key",
      examples: [
        { prompt: "Which node does A* expand next?", options: [{ text: "B", correct: true }] },
      ],
    };
    const messages = [
      { role: "tool", content: JSON.stringify({ style_drafts: [{ name: style.name, style }] }) },
      {
        role: "assistant",
        toolCalls: [
          {
            id: "call-3",
            function: {
              name: "save_style",
              arguments: JSON.stringify({ yaml: "id: ai.trace_astar\nname: Trace A* by hand\n" }),
            },
          },
        ],
      },
    ];
    const call = findCall(messages, { id: "i", reason: "tool_call", toolCallId: "call-3" });
    expect(call?.args.draft).toEqual(style);
    render(<ApprovalCardView call={call as NonNullable<typeof call>} onDecide={() => {}} />);
    expect(screen.getByText("Which node does A* expand next?")).toBeTruthy();
    expect(screen.getByRole("button", { name: /Approve/ })).toBeTruthy();
    expect(screen.getByRole("button", { name: /Reject/ })).toBeTruthy();
  });

  it("names the subject and question types by their labels on the subject card", () => {
    const messages = [
      {
        role: "tool",
        content: JSON.stringify({
          subjects: [{ id: "custom", label: "Something else" }],
          question_types: [{ id: "multiple_choice", label: "Multiple choice" }],
        }),
      },
      {
        role: "assistant",
        toolCalls: [
          {
            id: "call-4",
            function: {
              name: "set_course_subject",
              arguments: '{"subject":"custom","question_types":["multiple_choice"]}',
            },
          },
        ],
      },
    ];
    const call = findCall(messages, { id: "i", reason: "tool_call", toolCallId: "call-4" });
    const { title, lines } = describeCall(call as NonNullable<typeof call>);
    expect(title).toBe("Set the course's subject to Something else");
    expect(lines[0]).toBe("Question types: Multiple choice");
  });
});
