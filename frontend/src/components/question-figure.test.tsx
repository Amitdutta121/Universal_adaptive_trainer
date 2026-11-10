import { render, screen, waitFor } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import type { QuestionFigure as Figure } from "@/lib/api/types";
import { QuestionBody } from "./question-body";
import { QuestionFigure } from "./question-figure";

vi.mock("mermaid", () => ({
  default: {
    initialize: vi.fn(),
    render: vi.fn(async () => ({ svg: '<svg data-testid="diagram"></svg>' })),
  },
}));

const charts = vi.hoisted(() => [] as { type: string; data: unknown; options: unknown }[]);
vi.mock("chart.js/auto", () => ({
  default: class {
    constructor(_canvas: unknown, config: { type: string; data: unknown; options: unknown }) {
      charts.push(config);
    }
    destroy() {}
  },
}));

const DIAGRAM: Figure = {
  kind: "diagram",
  source: "flowchart TD\n A-->B",
  alt: "A points to B.",
  caption: "Two nodes.",
};
const SCATTER: Figure = {
  kind: "chart",
  alt: "Points rise to the right.",
  caption: "",
  chart: {
    type: "scatter",
    data: { labels: [], datasets: [{ label: "Runs", data: [{ x: 1, y: 2 }] }] },
    x_title: "Size",
    y_title: "Time (s)",
  },
};
const COMPUTED: Figure = {
  kind: "computed",
  file: `4/${"a".repeat(64)}.svg`,
  alt: "A grid with walls.",
  caption: "Dark cells are walls.",
};

describe("QuestionFigure", () => {
  it("draws a diagram with its alt text", async () => {
    render(<QuestionFigure figure={DIAGRAM} />);
    await waitFor(() => expect(screen.getByRole("img", { name: "A points to B." })).toBeTruthy());
    expect(screen.getByTestId("diagram")).toBeTruthy();
    expect(screen.getByText("Two nodes.")).toBeTruthy();
  });

  it("draws an x/y scatter chart with axis titles", async () => {
    charts.length = 0;
    render(<QuestionFigure figure={SCATTER} />);
    expect(screen.getByRole("img", { name: "Points rise to the right." })).toBeTruthy();
    await waitFor(() => expect(charts).toHaveLength(1));
    expect(charts[0]).toMatchObject({
      type: "scatter",
      data: { datasets: [{ data: [{ x: 1, y: 2 }] }] },
      options: {
        scales: {
          x: { title: { display: true, text: "Size" } },
          y: { title: { display: true, text: "Time (s)" } },
        },
      },
    });
  });

  it("shows a computed figure through <img> from the figure route, never inline", () => {
    const { container } = render(<QuestionFigure figure={COMPUTED} />);
    const image = screen.getByRole("img", { name: "A grid with walls." });
    expect(image.tagName).toBe("IMG");
    expect(image.getAttribute("src")).toBe(`/api/figures/${COMPUTED.file}`);
    expect(image.className).toContain("max-h-[22rem]");
    expect(container.querySelector("svg")).toBeNull();
  });
});

describe("QuestionBody", () => {
  it("shows the prompt and the figure under it", () => {
    render(<QuestionBody prompt="How many moves?" figure={COMPUTED} />);
    expect(screen.getByText("How many moves?")).toBeTruthy();
    expect(screen.getByRole("img", { name: "A grid with walls." })).toBeTruthy();
  });

  it("shows only the prompt when there is no figure", () => {
    render(<QuestionBody prompt="How many moves?" figure={null} />);
    expect(screen.getByText("How many moves?")).toBeTruthy();
    expect(screen.queryByRole("img")).toBeNull();
  });
});
