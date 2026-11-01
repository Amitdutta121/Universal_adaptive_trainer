/**
 * Flow test for the code-tracer tutorial prototype: stepping (button and keys), reset, switching
 * traces, auto-play's guard rails, and predict-then-reveal. Also checks the recorded traces are
 * self-consistent, since the UI trusts them.
 */

import { act, fireEvent, render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { PLAY_DELAY_MS } from "./components/use-trace-runner";
import { TRACES, TRY_ANSWER, TRY_TRACE } from "./mock-data";
import { TutorialsTraceExperience } from "./tutorials-trace-experience";

function stubMatchMedia(reduced: boolean) {
  vi.stubGlobal(
    "matchMedia",
    vi.fn().mockImplementation((query: string) => ({
      matches: reduced && query.includes("prefers-reduced-motion"),
      media: query,
      onchange: null,
      addEventListener: vi.fn(),
      removeEventListener: vi.fn(),
      addListener: vi.fn(),
      removeListener: vi.fn(),
      dispatchEvent: vi.fn(),
    })),
  );
}

beforeEach(() => {
  stubMatchMedia(false);
});

afterEach(() => {
  vi.useRealTimers();
  vi.unstubAllGlobals();
});

/** The trace under the segmented control (the page has a second player under "Now you try"). */
const tracer = () => within(screen.getByRole("tabpanel"));
const tryIt = () => within(screen.getByRole("region", { name: "Now you try" }));
const caption = (scope: ReturnType<typeof within>) =>
  scope.getAllByRole("status")[0] as HTMLElement;
const outputOf = (scope: ReturnType<typeof within>) => scope.getByLabelText("Program output");
const variables = (scope: ReturnType<typeof within>) =>
  scope.getByText("Variables").parentElement as HTMLElement;
const currentLine = (scope: ReturnType<typeof within>) =>
  scope
    .getAllByRole("listitem")
    .find((item: HTMLElement) => item.getAttribute("aria-current") === "step");

describe("recorded traces", () => {
  it("keep every caption to 12 words and end where the snippet really ends", () => {
    for (const trace of [...TRACES, TRY_TRACE]) {
      for (const step of trace.steps) {
        expect(step.caption.split(/\s+/).length).toBeLessThanOrEqual(12);
        expect(step.line).toBeGreaterThanOrEqual(1);
        expect(step.line).toBeLessThanOrEqual(trace.code.split("\n").length);
      }
    }
    const finals = Object.fromEntries(TRACES.map((trace) => [trace.id, trace.steps.at(-1)]));
    expect(finals.list?.output).toEqual(["apple", "banana", "cherry"]);
    expect(finals.total?.vars).toMatchObject({ i: "3", total: "6" });
    expect(finals["off-by-one"]?.vars).toMatchObject({ i: "4", total: "10" });
    expect(TRY_TRACE.steps.at(-1)?.vars.total).toBe(TRY_ANSWER);
  });
});

describe("TutorialsTraceExperience", () => {
  it("starts before the first line: nothing highlighted, no variables, no output", () => {
    render(<TutorialsTraceExperience />);
    const trace = tracer();

    expect(caption(trace)).toHaveTextContent("Press Step to run the first line.");
    expect(currentLine(trace)).toBeUndefined();
    expect(trace.getByText("0 / 8")).toBeInTheDocument();
    expect(trace.getByText("Nothing yet.")).toBeInTheDocument();
    expect(outputOf(trace)).toHaveTextContent("Nothing printed yet.");
    expect(trace.getByRole("button", { name: "Reset" })).toBeDisabled();
  });

  it("steps one line at a time: marks the line, updates variables and output, announces the caption", async () => {
    const user = userEvent.setup();
    render(<TutorialsTraceExperience />);
    const trace = tracer();

    await user.click(trace.getByRole("button", { name: "Step" }));
    expect(currentLine(trace)).toHaveTextContent("fruits = [");
    expect(caption(trace)).toHaveTextContent("fruits is a list of three items.");
    expect(caption(trace)).toHaveAttribute("aria-live", "polite");

    await user.click(trace.getByRole("button", { name: "Step" }));
    expect(currentLine(trace)).toHaveTextContent("for fruit in fruits:");
    expect(caption(trace)).toHaveTextContent("fruit takes the next value: 'apple'");
    expect(variables(trace)).toHaveTextContent("fruit'apple'");

    await user.click(trace.getByRole("button", { name: "Step" }));
    expect(currentLine(trace)).toHaveTextContent("print(fruit)");
    expect(outputOf(trace)).toHaveTextContent("apple");
    expect(outputOf(trace)).not.toHaveTextContent("banana");
  });

  it("steps with the right arrow and with Space, and leaves Space to a focused button", async () => {
    const user = userEvent.setup();
    render(<TutorialsTraceExperience />);
    const trace = tracer();

    await user.click(trace.getByRole("button", { name: "Step" }));
    await user.keyboard("{ArrowRight}");
    expect(trace.getByText("2 / 8")).toBeInTheDocument();

    // Space on the focused Step button is the button's own press: one step, not two.
    await user.keyboard(" ");
    expect(trace.getByText("3 / 8")).toBeInTheDocument();

    await user.click(trace.getByRole("region", { name: /^Code\./ }));
    await user.keyboard(" ");
    expect(trace.getByText("4 / 8")).toBeInTheDocument();
  });

  it("runs to the end, shows the rule once, and Reset goes back to before the first line", async () => {
    const user = userEvent.setup();
    render(<TutorialsTraceExperience />);
    const trace = tracer();
    const step = trace.getByRole("button", { name: "Step" });

    for (let count = 0; count < 8; count += 1) await user.click(step);
    expect(trace.getByText("8 / 8")).toBeInTheDocument();
    expect(caption(trace)).toHaveTextContent("No values left. The loop stops.");
    expect(caption(trace)).toHaveTextContent("for hands you each item in turn");
    expect(outputOf(trace)).toHaveTextContent("apple");
    expect(outputOf(trace)).toHaveTextContent("cherry");
    expect(step).toBeDisabled();

    await user.click(trace.getByRole("button", { name: "Reset" }));
    expect(trace.getByText("0 / 8")).toBeInTheDocument();
    expect(caption(trace)).toHaveTextContent("Press Step to run the first line.");
    expect(currentLine(trace)).toBeUndefined();
    expect(outputOf(trace)).toHaveTextContent("Nothing printed yet.");
    expect(trace.getByRole("button", { name: "Step" })).toBeEnabled();
  });

  it("switches traces, starts each from zero, and shows the off-by-one against what was expected", async () => {
    const user = userEvent.setup();
    render(<TutorialsTraceExperience />);

    await user.click(tracer().getByRole("button", { name: "Step" }));
    await user.click(screen.getByRole("tab", { name: "Running total" }));
    expect(screen.getByRole("tab", { name: "Running total" })).toHaveAttribute(
      "aria-selected",
      "true",
    );
    expect(tracer().getByText("0 / 9")).toBeInTheDocument();
    expect(tracer().getAllByRole("listitem")[1]).toHaveTextContent("range(1, 4)");

    await user.click(screen.getByRole("tab", { name: "Off by one" }));
    const trace = tracer();
    expect(trace.getAllByRole("listitem")[1]).toHaveTextContent("range(1, 5)");
    expect(trace.getByText("0 / 11")).toBeInTheDocument();

    const step = trace.getByRole("button", { name: "Step" });
    for (let count = 0; count < 8; count += 1) await user.click(step);
    expect(caption(trace)).toHaveTextContent("i takes the next value: 4");
    expect(trace.queryByText(/expected 5/)).not.toBeInTheDocument();

    await user.click(step);
    expect(caption(trace)).toHaveTextContent("total was 6, add 4: now 10");
    await user.click(step);
    expect(caption(trace)).toHaveTextContent("No 5 comes: range(1, 5) stops before 5.");
    expect(trace.getByText("expected 5")).toBeInTheDocument();
    expect(variables(trace)).toHaveTextContent("i4expected 5");

    await user.click(step);
    expect(caption(trace)).toHaveTextContent("Prints 10, not 15. The 5 never ran.");
    expect(caption(trace)).toHaveTextContent("range(1, 6)");
    expect(outputOf(trace)).toHaveTextContent("10");
  });

  describe("auto-play", () => {
    it("never runs until Play is pressed, then steps on a timer and stops at the end", () => {
      vi.useFakeTimers();
      render(<TutorialsTraceExperience />);
      const trace = tracer();

      act(() => {
        vi.advanceTimersByTime(PLAY_DELAY_MS.slow * 5);
      });
      expect(trace.getByText("0 / 8")).toBeInTheDocument();

      fireEvent.click(trace.getByRole("button", { name: "Play" }));
      expect(trace.getByRole("button", { name: "Pause" })).toBeInTheDocument();
      act(() => {
        vi.advanceTimersByTime(PLAY_DELAY_MS.slow);
      });
      expect(trace.getByText("1 / 8")).toBeInTheDocument();

      fireEvent.click(trace.getByRole("button", { name: "Fast" }));
      expect(trace.getByRole("button", { name: "Fast" })).toHaveAttribute("aria-pressed", "true");
      act(() => {
        vi.advanceTimersByTime(PLAY_DELAY_MS.fast);
      });
      expect(trace.getByText("2 / 8")).toBeInTheDocument();

      // One timeout is scheduled per render, so walk the clock a step at a time.
      for (let tick = 0; tick < 8; tick += 1) {
        act(() => {
          vi.advanceTimersByTime(PLAY_DELAY_MS.fast);
        });
      }
      expect(trace.getByText("8 / 8")).toBeInTheDocument();
      expect(trace.getByRole("button", { name: "Replay" })).toBeInTheDocument();
    });

    it("pauses when the window loses focus and stays paused", () => {
      vi.useFakeTimers();
      render(<TutorialsTraceExperience />);
      const trace = tracer();

      fireEvent.click(trace.getByRole("button", { name: "Play" }));
      act(() => {
        vi.advanceTimersByTime(PLAY_DELAY_MS.slow);
      });
      expect(trace.getByText("1 / 8")).toBeInTheDocument();

      act(() => {
        window.dispatchEvent(new Event("blur"));
      });
      expect(trace.getByRole("button", { name: "Play" })).toBeInTheDocument();
      act(() => {
        vi.advanceTimersByTime(PLAY_DELAY_MS.slow * 5);
      });
      expect(trace.getByText("1 / 8")).toBeInTheDocument();
    });

    it("is switched off when the device asks for reduced motion; stepping still works", async () => {
      stubMatchMedia(true);
      const user = userEvent.setup();
      render(<TutorialsTraceExperience />);
      const trace = tracer();

      expect(await trace.findByRole("button", { name: "Play" })).toBeDisabled();
      expect(trace.getByText(/reduced motion/)).toBeInTheDocument();
      await user.click(trace.getByRole("button", { name: "Step" }));
      expect(trace.getByText("1 / 8")).toBeInTheDocument();
    });
  });

  describe("Now you try", () => {
    it("hides total and the output until a prediction is made and revealed", async () => {
      const user = userEvent.setup();
      render(<TutorialsTraceExperience />);
      const section = tryIt();

      expect(section.getByRole("button", { name: "Reveal" })).toBeDisabled();

      // Stepping to the end before revealing still shows "?" for total and for what print wrote.
      const step = section.getByRole("button", { name: "Step" });
      for (let count = 0; count < 9; count += 1) await user.click(step);
      expect(variables(section)).toHaveTextContent("n4");
      expect(variables(section)).toHaveTextContent("total?");
      expect(outputOf(section)).toHaveTextContent("?");
      expect(outputOf(section)).not.toHaveTextContent("9");

      await user.click(section.getByRole("radio", { name: "14" }));
      expect(section.getByRole("button", { name: "Reveal" })).toBeEnabled();
      await user.click(section.getByRole("button", { name: "Reveal" }));

      expect(variables(section)).toHaveTextContent("total9");
      expect(outputOf(section)).toHaveTextContent("9");
      expect(section.getByText(/Not 14\./)).toBeInTheDocument();
      expect(section.getByText(/That counts the 5/)).toBeInTheDocument();
      expect(section.getByRole("radio", { name: "9" })).toBeDisabled();
      expect(section.getByRole("button", { name: "Reveal" })).toBeDisabled();
    });

    it("confirms a right prediction and jumps the trace to its last step", async () => {
      const user = userEvent.setup();
      render(<TutorialsTraceExperience />);
      const section = tryIt();

      await user.click(section.getByRole("radio", { name: "9" }));
      await user.click(section.getByRole("button", { name: "Reveal" }));

      expect(section.getByText(/Yes, 9\./)).toBeInTheDocument();
      expect(section.getByText("9 / 9")).toBeInTheDocument();
      expect(variables(section)).toHaveTextContent("total9");
      // The trace above is untouched by the exercise.
      expect(tracer().getByText("0 / 8")).toBeInTheDocument();
    });
  });
});
