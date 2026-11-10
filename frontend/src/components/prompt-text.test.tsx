import { render } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { PromptText, previewSegments } from "./prompt-text";

describe("PromptText", () => {
  it("renders plain text unchanged", () => {
    const { container } = render(<PromptText text="Which statement is true?" />);
    expect(container.textContent).toBe("Which statement is true?");
  });

  it("renders inline code, fenced code and lists", () => {
    const { container } = render(
      <PromptText text={"Fix `f`.\n\n```python\nx = 1\n```\n\n- keep `f(s)`\n- return a `dict`"} />,
    );
    expect(container.querySelector("pre code")?.textContent).toBe("x = 1\n");
    expect(container.querySelectorAll("li")).toHaveLength(2);
    expect(container.querySelector("p code")?.textContent).toBe("f");
  });

  it("renders math and tables", () => {
    const { container } = render(
      <PromptText text={"Find $f'(x)$.\n\n| a | b |\n| --- | --- |\n| 1 | 2 |"} />,
    );
    expect(container.querySelector(".katex")).not.toBeNull();
    expect(container.querySelector("table td")?.textContent).toBe("1");
  });

  it("drops raw html and images", () => {
    const { container } = render(
      <PromptText text={'<script>alert(1)</script> ok ![x](http://example.com/a.png)'} />,
    );
    expect(container.querySelector("script")).toBeNull();
    expect(container.querySelector("img")).toBeNull();
  });

  it("marks a question with a figure in the clamped preview", () => {
    const { container } = render(<PromptText text="How many moves?" variant="preview" hasFigure />);
    expect(container.textContent).toBe("[figure] How many moves?");
  });

  it("keeps angle brackets in prose such as Python reprs", () => {
    const { container } = render(<PromptText text={"It prints <class 'int'>."} />);
    expect(container.textContent).toContain("<class 'int'>");
  });
});

describe("previewSegments", () => {
  it("flattens markdown to one line with placeholders", () => {
    const text = "Output of:\n\n```python\nprint(1)\n```\n\n- use `x`\n- **bold**\n\n$$x^2$$";
    expect(previewSegments(text)).toEqual([
      { text: "Output of: ", code: false },
      { text: "[code]", muted: true },
      { text: " use ", code: false },
      { text: "x", code: true },
      { text: " bold ", code: false },
      { text: "[formula]", muted: true },
    ]);
  });

  it("collapses a table to one placeholder", () => {
    const segments = previewSegments("Data:\n\n| a | b |\n| --- | --- |\n| 1 | 2 |\n\nFind the mean.");
    expect(segments.map((segment) => segment.text)).toEqual(["Data: ", "[table]", " Find the mean."]);
  });
});
