/**
 * Flow test for the cheat-sheet prototype: static examples match CPython, the steppers redraw the
 * list and the number line's open/closed ends, the empty-range guard speaks plain words, and the
 * fold and the save toggle work. jsdom has no layout, so "one screen" and print are checked by
 * class/structure, not pixels.
 */

import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { pyListRepr, pyRange, SAVED_KEY, WHY_TEXT } from "./mock-data";
import { TutorialsSheetExperience } from "./tutorials-sheet-experience";

beforeEach(() => {
  window.localStorage.clear();
});

afterEach(() => {
  vi.restoreAllMocks();
});

const words = (text: string) => text.split(/\s+/).filter(Boolean).length;

const readout = () => screen.getByTestId("range-list").textContent;
const lineDots = () =>
  screen
    .getAllByTestId(/^line-(start|dot)$/)
    .filter((el) => el.getAttribute("data-state") !== "none");

describe("range helpers", () => {
  // Values below were printed by CPython 3 (`print(list(range(...)))`).
  it("match Python for the cheat-sheet examples", () => {
    expect(pyRange(4)).toEqual([0, 1, 2, 3]);
    expect(pyRange(1, 4)).toEqual([1, 2, 3]);
    expect(pyRange(0, 10, 3)).toEqual([0, 3, 6, 9]);
    expect(pyRange(1, 5)).toEqual([1, 2, 3, 4]);
    expect(pyRange(4, 1)).toEqual([]);
    expect(pyRange(3, 3)).toEqual([]);
    expect(pyListRepr([])).toBe("[]");
    expect(pyListRepr(pyRange(1, 5))).toBe("[1, 2, 3, 4]");
  });
});

describe("TutorialsSheetExperience", () => {
  it("shows the promise, five patterns with the results Python gives, and one watch-out", () => {
    render(<TutorialsSheetExperience />);

    expect(
      screen.getByRole("heading", { level: 1, name: /for loops and range\(\)/i }),
    ).toBeInTheDocument();
    expect(screen.getByRole("main")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: /Console/i })).toHaveAttribute("href", "/dashboard");
    expect(screen.getByText("Design prototype")).toBeInTheDocument();
    expect(screen.getByText(/Mock data/)).toBeInTheDocument();

    const rows = within(screen.getByRole("list", { name: "Patterns" })).getAllByRole("listitem");
    expect(rows).toHaveLength(5);
    const expected: [RegExp, string][] = [
      [/range\(4\)/, "0 1 2 3"],
      [/range\(1, 4\)/, "1 2 3"],
      [/range\(0, 10, 3\)/, "0 3 6 9"],
      [/for x in \["a", "b"\]/, "a b"],
      [/total \+= n/, "total = 8"],
    ];
    expected.forEach(([code, result], index) => {
      expect(rows[index]).toHaveTextContent(code);
      expect(within(rows[index]).getByText(result)).toBeInTheDocument();
    });

    const watch = screen.getByRole("complementary", { name: "Watch out" });
    expect(watch).toHaveTextContent("range(1, 5) gives 1 2 3 4. It never reaches 5.");
    expect(watch).toHaveTextContent("range(1, 6)");
  });

  it("keeps the first view to roughly 90 words of reading, and the fold under 80", () => {
    render(<TutorialsSheetExperience />);
    const article = screen.getByRole("article");
    const svgText = article.querySelector("svg")?.textContent ?? "";
    const firstView = words(article.textContent ?? "") - words(svgText);
    expect(firstView).toBeLessThanOrEqual(100);
    expect(words(WHY_TEXT.replaceAll("`", ""))).toBeLessThanOrEqual(80);
  });

  it("starts on range(1, 5): four filled dots and an open stop at 5", () => {
    render(<TutorialsSheetExperience />);

    expect(screen.getByTestId("range-call")).toHaveTextContent("list(range(1, 5))");
    expect(readout()).toBe("[1, 2, 3, 4]");
    expect(lineDots()).toHaveLength(4);
    expect(screen.getByTestId("line-start")).toHaveAttribute("data-state", "included");
    expect(screen.getByTestId("line-stop")).toHaveAttribute("data-state", "excluded");
    expect(screen.getByTestId("range-note")).toHaveTextContent("Last number is 4, not 5.");
  });

  it("has labelled steppers, a live result region and a text alternative for the number line", () => {
    render(<TutorialsSheetExperience />);

    for (const name of [/Decrease start/, /Increase start/, /Decrease stop/, /Increase stop/]) {
      expect(screen.getByRole("button", { name })).toBeInTheDocument();
    }
    const live = document.querySelector('[role="status"][aria-live="polite"]');
    expect(live).not.toBeNull();
    expect(live).toContainElement(screen.getByTestId("range-list"));
    const line = screen.getByRole("img", { name: /Number line from 0 to 10, start 1, stop 5/ });
    expect(line.getAttribute("aria-describedby")).toBe(live?.id);
  });

  it("redraws the list and the line as start and stop change", async () => {
    const user = userEvent.setup();
    render(<TutorialsSheetExperience />);

    await user.click(screen.getByRole("button", { name: "Increase stop" }));
    expect(screen.getByTestId("stop-value")).toHaveTextContent("6");
    expect(readout()).toBe("[1, 2, 3, 4, 5]");
    expect(lineDots()).toHaveLength(5);
    expect(screen.getByTestId("line-stop")).toHaveAttribute("data-state", "excluded");
    expect(screen.getByTestId("range-note")).toHaveTextContent("Last number is 5, not 6.");

    await user.click(screen.getByRole("button", { name: "Decrease start" }));
    expect(screen.getByTestId("start-value")).toHaveTextContent("0");
    expect(readout()).toBe("[0, 1, 2, 3, 4, 5]");
    expect(lineDots()).toHaveLength(6);
    expect(screen.getByTestId("line-start")).toHaveAttribute("data-state", "included");

    // The lower bound is a disabled button, not a silent no-op.
    expect(screen.getByRole("button", { name: "Decrease start" })).toBeDisabled();
  });

  it("says an empty range in plain words when stop is not bigger than start", async () => {
    const user = userEvent.setup();
    render(<TutorialsSheetExperience />);
    const decreaseStop = screen.getByRole("button", { name: "Decrease stop" });

    // stop 5 -> 1 equals start 1
    for (let i = 0; i < 4; i += 1) await user.click(decreaseStop);
    expect(screen.getByTestId("range-call")).toHaveTextContent("list(range(1, 1))");
    expect(readout()).toBe("[]");
    expect(screen.getByTestId("range-note")).toHaveTextContent(
      "Nothing to loop over: stop must be bigger than start.",
    );
    expect(screen.queryAllByTestId("line-dot")).toHaveLength(0);
    expect(screen.getByTestId("line-start")).toHaveAttribute("data-state", "none");
    expect(screen.getByTestId("line-stop")).toHaveAttribute("data-state", "excluded");

    // stop below start is empty too
    await user.click(decreaseStop);
    expect(readout()).toBe("[]");
    expect(screen.getByTestId("range-note")).toHaveTextContent(/Nothing to loop over/);

    // ... and it recovers
    await user.click(screen.getByRole("button", { name: "Increase stop" }));
    await user.click(screen.getByRole("button", { name: "Increase stop" }));
    expect(readout()).toBe("[1]");
    expect(screen.getByTestId("line-start")).toHaveAttribute("data-state", "included");
  });

  it("folds the longer explanation until asked", async () => {
    const user = userEvent.setup();
    render(<TutorialsSheetExperience />);
    const trigger = screen.getByRole("button", { name: /Show me why/i });

    expect(trigger).toHaveAttribute("aria-expanded", "false");
    expect(screen.queryByText(/quits the moment it would reach stop/)).not.toBeInTheDocument();

    await user.click(trigger);
    expect(trigger).toHaveAttribute("aria-expanded", "true");
    expect(screen.getByText(/quits the moment it would reach stop/)).toBeVisible();

    await user.click(trigger);
    expect(trigger).toHaveAttribute("aria-expanded", "false");
  });

  it("toggles Save to my notes and remembers it in localStorage", async () => {
    const user = userEvent.setup();
    const { unmount } = render(<TutorialsSheetExperience />);
    const save = screen.getByRole("button", { name: /Save to my notes/i });

    expect(save).toHaveAttribute("aria-pressed", "false");
    await user.click(save);
    expect(save).toHaveAttribute("aria-pressed", "true");
    expect(window.localStorage.getItem(SAVED_KEY)).toBe("1");
    expect(screen.getByText("Saved on this device")).toBeInTheDocument();

    unmount();
    render(<TutorialsSheetExperience />);
    expect(
      await screen.findByRole("button", { name: /Save to my notes/i, pressed: true }),
    ).toBeInTheDocument();

    await user.click(screen.getByRole("button", { name: /Save to my notes/i }));
    expect(window.localStorage.getItem(SAVED_KEY)).toBeNull();
  });

  it("still works when localStorage is blocked", async () => {
    const user = userEvent.setup();
    vi.spyOn(Storage.prototype, "getItem").mockImplementation(() => {
      throw new Error("blocked");
    });
    vi.spyOn(Storage.prototype, "setItem").mockImplementation(() => {
      throw new Error("blocked");
    });
    render(<TutorialsSheetExperience />);

    const save = screen.getByRole("button", { name: /Save to my notes/i });
    await user.click(save);
    expect(save).toHaveAttribute("aria-pressed", "true");
    expect(readout()).toBe("[1, 2, 3, 4]");
  });

  it("is laid out to print on one page: chrome and controls hidden", () => {
    render(<TutorialsSheetExperience />);
    expect(screen.getByRole("banner")).toHaveClass("print:hidden");
    expect(screen.getByRole("button", { name: /Save to my notes/i }).parentElement).toHaveClass(
      "print:hidden",
    );
    expect(screen.getByRole("button", { name: /Show me why/i }).parentElement).toHaveClass(
      "print:hidden",
    );
    expect(screen.getByRole("group", { name: "start" }).parentElement).toHaveClass("print:hidden");
  });
});
