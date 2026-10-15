import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { StudentTutorialBlocks } from "./student-tutorial-blocks";

function block(id: number, guidance_level: "worked" | "faded" | "cue", markdown: string) {
  return {
    id,
    recipe_id: "py.misconception_line",
    guidance_level,
    renderer: "markdown" as const,
    payload: { markdown },
  };
}

describe("student tutorial blocks", () => {
  it("draw nothing without blocks, so the card keeps its explanation", () => {
    const { container } = render(<StudentTutorialBlocks blocks={[]} moment="after" />);
    expect(container).toBeEmptyDOMElement();
  });

  it("head worked blocks after a wrong answer and draw each through the registry", () => {
    render(
      <StudentTutorialBlocks
        blocks={[block(1, "worked", "First **step**"), block(2, "worked", "Second step")]}
        moment="after"
      />,
    );
    expect(screen.getByRole("region", { name: "Work through it" })).toBeInTheDocument();
    expect(screen.getByText("step")).toBeInTheDocument();
    expect(screen.getByText("Second step")).toBeInTheDocument();
  });

  it("name lighter guidance and pre-teaching for what they are", () => {
    const { rerender } = render(
      <StudentTutorialBlocks blocks={[block(3, "cue", "A reminder")]} moment="after" />,
    );
    expect(screen.getByRole("region", { name: "Remember" })).toBeInTheDocument();
    rerender(<StudentTutorialBlocks blocks={[block(4, "worked", "Intro")]} moment="before" />);
    expect(screen.getByRole("region", { name: "Before you start" })).toBeInTheDocument();
  });
});
