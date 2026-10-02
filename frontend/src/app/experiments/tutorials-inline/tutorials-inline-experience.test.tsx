/**
 * Flow test for the inline-help prototype (variant C): wrong answer -> one-line reason -> refresher
 * drawer -> "Got it" -> new question; the same misconception twice -> fuller version; correct path.
 */

import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it } from "vitest";
import { QUESTIONS, REFRESHERS, SOURCE_LINE } from "./mock-data";
import { TutorialsInlineExperience } from "./tutorials-inline-experience";

type User = ReturnType<typeof userEvent.setup>;

async function answer(user: User, name: string) {
  await user.click(screen.getByRole("radio", { name }));
  await user.click(screen.getByRole("button", { name: /Submit answer/i }));
}

describe("TutorialsInlineExperience", () => {
  it("renders standalone with the prototype label, console link and mock note", () => {
    render(<TutorialsInlineExperience />);
    expect(screen.getByText("Design prototype")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: /Console/i })).toHaveAttribute("href", "/dashboard");
    expect(screen.getByText(/Mock data/)).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: "Question 1 of 3" })).toBeInTheDocument();
  });

  it("locks the submit button until an option is picked", async () => {
    const user = userEvent.setup();
    render(<TutorialsInlineExperience />);
    expect(screen.getByRole("button", { name: /Submit answer/i })).toBeDisabled();
    await user.click(screen.getByRole("radio", { name: "10" }));
    expect(screen.getByRole("button", { name: /Submit answer/i })).toBeEnabled();
  });

  it("wrong answer -> reason in a live region -> drawer -> Got it -> new question", async () => {
    const user = userEvent.setup();
    render(<TutorialsInlineExperience />);

    await answer(user, "10");

    // One-line reason for THIS option, inside the aria-live region, which also has focus.
    const live = screen.getByRole("status");
    expect(live).toHaveAttribute("aria-live", "polite");
    expect(within(live).getByText("Not quite")).toBeInTheDocument();
    expect(within(live).getByText(/range\(1, 4\) stops before 4/)).toBeInTheDocument();
    expect(live).toHaveFocus();

    // Nothing is shown until the student asks for it.
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();

    const trigger = screen.getByRole("button", { name: /Need a refresher\? 30 seconds/ });
    await user.click(trigger);

    const dialog = await screen.findByRole("dialog", { name: REFRESHERS.stop_included.title });
    // First time: the 3-line version, one snippet, the quiet source line, no "second time" note.
    for (const line of REFRESHERS.stop_included.short) {
      expect(within(dialog).getByText(line)).toBeInTheDocument();
    }
    expect(within(dialog).getByText("Output")).toBeInTheDocument();
    expect(within(dialog).getByText(new RegExp(`generated from ${SOURCE_LINE.replace(/[().]/g, "\\$&")}`))).toBeInTheDocument();
    expect(within(dialog).getByText(/Why you.re seeing this/)).toBeInTheDocument();
    expect(within(dialog).queryByText(/second time/)).not.toBeInTheDocument();
    expect(
      within(dialog).queryByRole("button", { name: /fuller version/i }),
    ).not.toBeInTheDocument();

    await user.click(within(dialog).getByRole("button", { name: "Got it, try another" }));

    await waitFor(() => expect(screen.queryByRole("dialog")).not.toBeInTheDocument());
    const heading = screen.getByRole("heading", { name: "Question 2 of 3" });
    expect(heading).toBeInTheDocument();
    expect(heading).toHaveFocus();
    // Back in practice with a clean, unanswered question.
    expect(screen.getByRole("button", { name: /Submit answer/i })).toBeDisabled();
  });

  it("returns focus to the refresher button when the drawer is closed with Escape", async () => {
    const user = userEvent.setup();
    render(<TutorialsInlineExperience />);

    await answer(user, "10");
    const trigger = screen.getByRole("button", { name: /Need a refresher\? 30 seconds/ });
    await user.click(trigger);
    await screen.findByRole("dialog");
    await user.keyboard("{Escape}");

    await waitFor(() => expect(screen.queryByRole("dialog")).not.toBeInTheDocument());
    await waitFor(() => expect(trigger).toHaveFocus());
    // Still on the same question: closing the drawer does not advance.
    expect(screen.getByRole("heading", { name: "Question 1 of 3" })).toBeInTheDocument();
  });

  it("the second time the same misconception is picked, the drawer says so and offers the fuller version", async () => {
    const user = userEvent.setup();
    render(<TutorialsInlineExperience />);

    // Q1: stop value included (10).
    await answer(user, "10");
    await user.click(screen.getByRole("button", { name: /Next question/ }));

    // Q2: stop value included again (0 1 2 3).
    await screen.findByRole("heading", { name: "Question 2 of 3" });
    await answer(user, "0 1 2 3");
    expect(screen.getByText(/That includes 3/)).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: /Need a refresher\? 30 seconds/ }));

    const dialog = await screen.findByRole("dialog", { name: REFRESHERS.stop_included.title });
    expect(within(dialog).getByText(/This is the second time/)).toBeInTheDocument();
    // Still the short version until asked.
    expect(within(dialog).queryByText(REFRESHERS.stop_included.full[5])).not.toBeInTheDocument();

    await user.click(within(dialog).getByRole("button", { name: /Show the fuller version \(6 lines\)/ }));
    for (const line of REFRESHERS.stop_included.full) {
      expect(within(dialog).getByText(line)).toBeInTheDocument();
    }
    expect(REFRESHERS.stop_included.full).toHaveLength(6);

    await user.click(within(dialog).getByRole("button", { name: "Got it, try another" }));
    expect(await screen.findByRole("heading", { name: "Question 3 of 3" })).toBeInTheDocument();
  });

  it("a different misconception the second time still gets the short, first-time refresher", async () => {
    const user = userEvent.setup();
    render(<TutorialsInlineExperience />);

    await answer(user, "10"); // stop_included
    await user.click(screen.getByRole("button", { name: /Next question/ }));
    await screen.findByRole("heading", { name: "Question 2 of 3" });
    await answer(user, "1 2 3"); // start_at_one
    await user.click(screen.getByRole("button", { name: /Need a refresher\? 30 seconds/ }));

    const dialog = await screen.findByRole("dialog", { name: REFRESHERS.start_at_one.title });
    expect(within(dialog).queryByText(/second time/)).not.toBeInTheDocument();
  });

  it("correct answer path: reason, no refresher, next question, then the summary", async () => {
    const user = userEvent.setup();
    render(<TutorialsInlineExperience />);

    await answer(user, "6");
    expect(screen.getByText("Correct")).toBeInTheDocument();
    expect(screen.getByText(/1 \+ 2 \+ 3 = 6/)).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /Need a refresher/ })).not.toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: /Next question/ }));

    await screen.findByRole("heading", { name: "Question 2 of 3" });
    await answer(user, "0 1 2");
    await user.click(screen.getByRole("button", { name: /Next question/ }));

    await screen.findByRole("heading", { name: "Question 3 of 3" });
    await answer(user, "4");
    await user.click(screen.getByRole("button", { name: /See summary/ }));

    const done = await screen.findByRole("heading", { name: "Set finished" });
    expect(done).toHaveFocus();
    expect(screen.getByText("3 of 3 correct.")).toBeInTheDocument();

    await user.click(screen.getByRole("button", { name: /Start over/ }));
    expect(await screen.findByRole("heading", { name: "Question 1 of 3" })).toBeInTheDocument();
  });

  it("every wrong option in the bank maps to a misconception that has a refresher", () => {
    for (const question of QUESTIONS) {
      expect(question.options.filter((option) => option.correct)).toHaveLength(1);
      for (const option of question.options.filter((o) => !o.correct)) {
        expect(option.misconception).toBeDefined();
        expect(option.misconception && REFRESHERS[option.misconception]).toBeDefined();
        expect(option.reason.length).toBeGreaterThan(0);
      }
    }
    for (const refresher of Object.values(REFRESHERS)) {
      expect(refresher.short).toHaveLength(3);
      expect(refresher.full).toHaveLength(6);
    }
  });
});
