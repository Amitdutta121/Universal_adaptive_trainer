/**
 * Flow test for the tutorial prototype: the reader opens on the recommended tutorial, code can be
 * run, a self-check gives feedback, progress is kept, and the outline moves between tutorials.
 */

import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it } from "vitest";
import { tokenizePython } from "./components/tutorial-blocks";
import { TUTORIALS } from "./mock-tutorials";
import { TutorialsExperience } from "./tutorials-experience";

beforeEach(() => {
  window.localStorage.clear();
  window.history.replaceState(null, "", "/experiments/tutorials");
});

const outline = () => screen.getAllByRole("navigation", { name: "Course outline" })[0] as HTMLElement;

describe("TutorialsExperience", () => {
  it("opens on the tutorial the student was recommended, and says why", () => {
    render(<TutorialsExperience />);

    expect(screen.getByRole("heading", { level: 1, name: "for loops and range()" })).toBeInTheDocument();
    expect(screen.getByLabelText("Why this tutorial")).toHaveTextContent(/missed 2 of your last 3/);
  });

  it("shows a code block's output only after Run, and hides it again", async () => {
    const user = userEvent.setup();
    render(<TutorialsExperience />);
    expect(screen.queryByText("CHERRY")).not.toBeInTheDocument();

    await user.click(screen.getAllByRole("button", { name: "Run" })[0] as HTMLElement);
    expect(screen.getByText(/CHERRY/)).toBeInTheDocument();

    await user.click(screen.getByRole("button", { name: "Hide output" }));
    expect(screen.queryByText(/CHERRY/)).not.toBeInTheDocument();
  });

  it("marks a wrong answer without giving up the right one, then confirms the right one", async () => {
    const user = userEvent.setup();
    render(<TutorialsExperience />);
    const check = screen.getByRole("group", { name: /Check yourself: What is total at the end\?/ });

    await user.click(within(check).getByLabelText(/^C\s*10$/));
    expect(within(check).getByRole("status")).toHaveTextContent(/Not quite/);
    expect(within(check).getByRole("status")).not.toHaveTextContent(/1 \+ 2 \+ 3 = 6/);

    await user.click(within(check).getByLabelText(/^B\s*6$/));
    expect(within(check).getByRole("status")).toHaveTextContent(/Correct/);
    expect(screen.getByText(/1 of 1 check right/)).toBeInTheDocument();
  });

  it("keeps a tutorial marked as done, counts it in the outline, and remembers it", async () => {
    const user = userEvent.setup();
    const { unmount } = render(<TutorialsExperience />);
    expect(within(outline()).getByText("2/5")).toBeInTheDocument();

    await user.click(screen.getByRole("button", { name: "Mark as done" }));
    expect(within(outline()).getByText("3/5")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Marked as done" })).toBeInTheDocument();

    unmount();
    render(<TutorialsExperience />);
    expect(within(outline()).getByText("3/5")).toBeInTheDocument();
  });

  it("moves to another tutorial from the outline and puts it in the address", async () => {
    const user = userEvent.setup();
    render(<TutorialsExperience />);

    await user.click(within(outline()).getByRole("button", { name: /while loops/ }));

    expect(screen.getByRole("heading", { level: 1, name: "while loops" })).toBeInTheDocument();
    expect(window.location.hash).toBe("#while-loops");
    // Its checks start fresh, and the recommendation belongs to the other tutorial.
    expect(screen.queryByLabelText("Why this tutorial")).not.toBeInTheDocument();
    expect(screen.getByText(/0 of 1 check right/)).toBeInTheDocument();
  });

  it("opens the tutorial named in the address", () => {
    window.history.replaceState(null, "", "/experiments/tutorials#functions");
    render(<TutorialsExperience />);

    expect(screen.getByRole("heading", { level: 1, name: "Defining and calling functions" })).toBeInTheDocument();
  });

  it("does not offer Run for a snippet that must not be run, and says why", async () => {
    const user = userEvent.setup();
    render(<TutorialsExperience />);
    await user.click(within(outline()).getByRole("button", { name: /while loops/ }));

    expect(screen.getByText(/this loop never stops/)).toBeInTheDocument();
    // Two runnable snippets in this tutorial, and the third has no Run button.
    expect(screen.getAllByRole("button", { name: "Run" })).toHaveLength(2);
  });
});

describe("the mock content", () => {
  it("has exactly one correct option in every check, and a reason for every option", () => {
    for (const tutorial of TUTORIALS) {
      for (const section of tutorial.sections) {
        for (const block of section.blocks) {
          if (block.kind !== "check") continue;
          expect(block.options.filter((option) => option.correct), block.id).toHaveLength(1);
          for (const option of block.options) expect(option.why.length, block.id).toBeGreaterThan(10);
        }
      }
    }
  });

  it("only cites sources that exist", () => {
    for (const tutorial of TUTORIALS) {
      for (const section of tutorial.sections) {
        for (const block of section.blocks) {
          if (block.kind === "p" && block.cite) {
            expect(tutorial.sources[block.cite - 1], `${tutorial.id} cites [${block.cite}]`).toBeDefined();
          }
        }
      }
    }
  });
});

describe("tokenizePython", () => {
  it("separates keywords, builtins, strings, numbers and comments, and loses no text", () => {
    const source = 'for i in range(3):  # count\n    print(f"n={i}", 4.5)';
    const tokens = tokenizePython(source);

    expect(tokens.map((token) => token.text).join("")).toBe(source);
    const kindOf = (text: string) => tokens.find((token) => token.text === text)?.kind;
    expect(kindOf("for")).toBe("keyword");
    expect(kindOf("range")).toBe("builtin");
    expect(kindOf("3")).toBe("number");
    expect(kindOf("# count")).toBe("comment");
    expect(kindOf('f"n={i}"')).toBeUndefined();
    expect(kindOf('"n={i}"')).toBe("string");
    expect(kindOf("4.5")).toBe("number");
  });

  it("does not colour a keyword inside a string or a comment", () => {
    const tokens = tokenizePython('x = "for while"  # if else');
    expect(tokens.filter((token) => token.kind === "keyword")).toEqual([]);
  });
});
