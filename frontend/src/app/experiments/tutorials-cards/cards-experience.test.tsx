/**
 * Flow test for the micro-card tutorial: paging with the buttons and the arrow keys, the progress
 * segments, the one-question check, and the way out to practice. Also asserts the copy budget
 * (headline <= 8 words, body <= 25 words) so the "far less reading" promise cannot drift.
 */

import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it } from "vitest";
import { CardsExperience } from "./cards-experience";
import { CARDS, PRACTICE_HREF } from "./mock-data";

const words = (text: string) => text.trim().split(/\s+/).length;

describe("copy budget", () => {
  it("keeps every headline to 8 words and every body to 25", () => {
    for (const card of CARDS) {
      expect(words(card.headline), card.id).toBeLessThanOrEqual(8);
      if (card.kind === "lesson") expect(words(card.body), card.id).toBeLessThanOrEqual(25);
    }
  });
});

describe("CardsExperience", () => {
  it("starts on the first card with Back disabled", () => {
    render(<CardsExperience />);
    expect(screen.getByRole("heading", { level: 1, name: CARDS[0].headline })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /^Back$/ })).toBeDisabled();
    expect(screen.getByRole("button", { name: /^Go to card 1 of 8$/ })).toHaveAttribute("aria-current", "step");
  });

  it("pages with Next/Back and announces the card", async () => {
    const user = userEvent.setup();
    render(<CardsExperience />);

    await user.click(screen.getByRole("button", { name: /^Next$/ }));
    expect(screen.getByRole("heading", { level: 1, name: CARDS[1].headline })).toBeInTheDocument();
    expect(screen.getByText(`Card 2 of ${CARDS.length}: ${CARDS[1].headline}`)).toBeInTheDocument();
    expect(screen.getByText("Output")).toBeInTheDocument();

    await user.click(screen.getByRole("button", { name: /^Back$/ }));
    expect(screen.getByRole("heading", { level: 1, name: CARDS[0].headline })).toBeInTheDocument();
  });

  it("pages with the arrow keys and stops at both ends", async () => {
    const user = userEvent.setup();
    render(<CardsExperience />);

    await user.keyboard("{ArrowLeft}");
    expect(screen.getByRole("heading", { level: 1, name: CARDS[0].headline })).toBeInTheDocument();

    await user.keyboard("{ArrowRight}{ArrowRight}");
    expect(screen.getByRole("heading", { level: 1, name: CARDS[2].headline })).toBeInTheDocument();

    await user.keyboard("{ArrowRight>10/}");
    expect(screen.getByRole("heading", { level: 1, name: CARDS.at(-1)?.headline })).toBeInTheDocument();
  });

  it("jumps with a progress segment", async () => {
    const user = userEvent.setup();
    render(<CardsExperience />);
    await user.click(screen.getByRole("button", { name: /^Go to card 7 of 8$/ }));
    expect(screen.getByRole("heading", { level: 1, name: CARDS[6].headline })).toBeInTheDocument();
    expect(screen.getByText("[1, 2, 3, 4, 5]", { exact: false })).toBeInTheDocument();
  });

  it("walks the whole flow: check, wrong answer, right answer, practice link", async () => {
    const user = userEvent.setup();
    render(<CardsExperience />);

    for (let step = 0; step < CARDS.length - 1; step++) {
      await user.click(screen.getByRole("button", { name: /^Next$/ }));
    }
    expect(screen.getByRole("heading", { level: 1, name: "One quick check" })).toBeInTheDocument();
    // No way forward until an answer is picked.
    expect(screen.queryByRole("link", { name: /Practice for loops/i })).not.toBeInTheDocument();
    expect(screen.getByText("Pick an answer")).toBeInTheDocument();

    await user.click(screen.getByRole("button", { name: "range(1, 5)" }));
    expect(screen.getByText("Not quite.")).toBeInTheDocument();
    expect(screen.getByText(/gives 1 to 4/)).toBeInTheDocument();

    await user.click(screen.getByRole("button", { name: "range(1, 6)" }));
    expect(screen.getByText("Correct.")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "range(1, 6)" })).toHaveAttribute("aria-pressed", "true");

    const practice = screen.getByRole("link", { name: /Practice for loops/i });
    expect(practice).toHaveAttribute("href", PRACTICE_HREF);
  });

  it("labels itself as a prototype with a way back to the console", () => {
    render(<CardsExperience />);
    expect(screen.getByText("Design prototype")).toBeInTheDocument();
    expect(screen.getByText(/Mock data/)).toBeInTheDocument();
    expect(screen.getByRole("link", { name: /Console/ })).toHaveAttribute("href", "/dashboard");
  });
});
