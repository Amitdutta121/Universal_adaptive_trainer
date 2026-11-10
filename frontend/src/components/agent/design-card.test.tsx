import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import { type CourseDesign, DesignCard } from "./design-card";
import { isSuperseded } from "./tool-renderers";

const DESIGN: CourseDesign = {
  design_id: "d1",
  title: "AI in Games",
  audience: "Upper-level CS students",
  topic_count: 1,
  subtopic_count: 2,
  styles_ready: true,
  recipes_ready: true,
  styles: [
    {
      name: "Trace A* by hand",
      question_type: "Multiple choice",
      summary: "Pick the next node A* expands.",
      new: true,
      used_by: 2,
    },
    {
      name: "Spot the wrong search claim",
      question_type: "True / false",
      summary: "Judge one claim about a search algorithm.",
      new: false,
      reused_from: "Catch a common misconception",
      used_by: 1,
    },
  ],
  recipes: [
    {
      name: "Step through the search",
      form: "Interactive page",
      summary: "Click through each expansion.",
      new: true,
      used_by: 2,
    },
  ],
  topics: [
    {
      name: "Search",
      subtopics: [
        {
          name: "A* search",
          description: "",
          styles: ["Trace A* by hand"],
          recipes: ["Step through the search"],
        },
        {
          name: "Breadth-first search",
          description: "",
          styles: ["Spot the wrong search claim"],
          recipes: ["Step through the search"],
        },
      ],
    },
  ],
  out_of_scope: ["Unity projects"],
};

describe("DesignCard", () => {
  it("shows every style, recipe and subtopic, and where a reused style came from", () => {
    render(<DesignCard design={DESIGN} ask={null} />);
    expect(screen.getByText("How students are checked.")).toBeTruthy();
    expect(screen.getByText("Reused: Catch a common misconception")).toBeTruthy();
    expect(screen.getByText("Breadth-first search")).toBeTruthy();
    expect(screen.getByText("Unity projects")).toBeTruthy();
    expect(screen.getByText("2 · 1 new")).toBeTruthy();
    // Read-only without a chat: no buttons.
    expect(screen.queryByRole("button")).toBeNull();
  });

  it("sends a follow-up for a row change, a removal, any change and approval", () => {
    const ask = vi.fn();
    render(<DesignCard design={DESIGN} ask={ask} />);

    fireEvent.click(screen.getByRole("button", { name: "Remove Trace A* by hand" }));
    expect(ask).toHaveBeenLastCalledWith('Remove the style "Trace A* by hand" from the design.');

    fireEvent.click(screen.getByRole("button", { name: "Change Step through the search" }));
    fireEvent.change(screen.getByPlaceholderText(/What should change about/), {
      target: { value: "use a diagram instead" },
    });
    fireEvent.submit(screen.getByPlaceholderText(/What should change about/));
    expect(ask).toHaveBeenLastCalledWith(
      'Change the recipe "Step through the search": use a diagram instead',
    );

    fireEvent.click(screen.getByRole("button", { name: /Approve design/ }));
    expect(ask).toHaveBeenLastCalledWith("Approve this design.");
  });

  it("says which parts are not suggested yet and offers approval only for a whole design", () => {
    render(<DesignCard design={{ ...DESIGN, recipes_ready: false }} ask={vi.fn()} />);
    expect(screen.getByText(/Tutorial recipes are not suggested/)).toBeTruthy();
    expect(screen.queryByText("Step through the search", { selector: "div" })).toBeNull();
    expect(screen.queryByRole("button", { name: /Approve design/ })).toBeNull();
  });

  it("shows the curriculum, the styles and the recipes as three cards", () => {
    render(<DesignCard design={DESIGN} ask={null} />);
    for (const title of ["Curriculum", "Question styles", "Tutorial recipes"]) {
      expect(screen.getByRole("heading", { level: 3, name: title })).toBeTruthy();
    }
  });

  it("shows an earlier version of a design as one line", () => {
    render(<DesignCard design={DESIGN} ask={vi.fn()} superseded />);
    expect(screen.getByText(/An earlier version of the course design/)).toBeTruthy();
    expect(screen.queryByText("Trace A* by hand")).toBeNull();
  });
});

describe("isSuperseded", () => {
  const shown = (id: string) => ({
    role: "assistant",
    toolCalls: [{ id, function: { name: "show_design" } }],
  });
  const result = (id: string, designId: string) => ({
    role: "tool",
    toolCallId: id,
    content: JSON.stringify({ design_id: designId }),
  });

  it("is true only when a later show_design shows the same design", () => {
    const messages = [shown("a"), result("a", "d1"), shown("b"), result("b", "d1")];
    expect(isSuperseded(messages, "a", "d1")).toBe(true);
    expect(isSuperseded(messages, "b", "d1")).toBe(false);
    const other = [shown("a"), result("a", "d1"), shown("b"), result("b", "d2")];
    expect(isSuperseded(other, "a", "d1")).toBe(false);
  });
});
