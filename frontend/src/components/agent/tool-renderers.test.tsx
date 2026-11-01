import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { StyleComparison, ToolStatusLine } from "./tool-renderers";

describe("StyleComparison", () => {
  it("puts the styles side by side, each with its first sample question", () => {
    render(
      <StyleComparison
        styles={[
          {
            id: "py.predict_output",
            name: "Predict what the code prints",
            summary: "Read code, say its output.",
            checked_by: "Runs the code",
            examples: [
              { prompt: "What does this print?", code: "print(1 + 1)" },
              { prompt: "Second" },
            ],
          },
          {
            id: "py.fix_one_bug",
            name: "Fix one bug",
            summary: "Find and fix the bug.",
            examples: [{ prompt: "Fix the loop." }],
          },
        ]}
      />,
    );
    expect(screen.getAllByRole("heading").map((h) => h.textContent)).toEqual([
      "Predict what the code prints",
      "Fix one bug",
    ]);
    expect(screen.getByText("print(1 + 1)")).toBeInTheDocument();
    expect(screen.queryByText("Second")).not.toBeInTheDocument();
  });
});

describe("ToolStatusLine", () => {
  it("names a finished tool", () => {
    render(<ToolStatusLine name="coverage_report" status="complete" result='{"gaps": []}' />);
    expect(screen.getByText("Check coverage")).toBeInTheDocument();
  });

  it("shows the app's refusal", () => {
    render(
      <ToolStatusLine
        name="import_material"
        status="complete"
        result='{"error": "This is not a YouTube link.", "detail": null}'
      />,
    );
    expect(screen.getByText("Import material — This is not a YouTube link.")).toBeInTheDocument();
  });
});

describe("agentErrorMessage", () => {
  it("reads the backend's refusal out of a failed run", async () => {
    const { agentErrorMessage } = await import("./agent-panel");
    const error = new Error(
      'HTTP 500: {"error":{"code":"configuration_error","message":"This feature needs an LLM provider and API key.","detail":"Set LLM_PROVIDER"}}',
    );
    expect(agentErrorMessage(error)).toBe("This feature needs an LLM provider and API key.");
    expect(agentErrorMessage(new Error("network down"))).toBe("network down");
  });
});
