import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";
import type { QuestionDetail } from "@/lib/api/types";

const mutateAsync = vi.fn();

vi.mock("@/lib/api/queries", () => ({
  useRegenerateFigureCopy: () => ({ mutateAsync, isPending: false }),
}));

vi.mock("@/components/question-body", () => ({
  QuestionBody: ({ prompt }: { prompt: string }) => <div>{prompt}</div>,
}));

import { QuestionFigureCopies } from "./question-figure-copies";

function detailWithCopies(): QuestionDetail {
  return {
    question: { id: 7 },
    figure_copies: [
      {
        ordinal: 0,
        seed: 11,
        prompt: "Copy A prompt",
        reference_solution: "3",
        content: { figure: { kind: "computed", file: "7/a.svg", alt: "A", caption: "" } },
      },
      {
        ordinal: 1,
        seed: 22,
        prompt: "Copy B prompt",
        reference_solution: "5",
        content: { figure: { kind: "computed", file: "7/b.svg", alt: "B", caption: "" } },
      },
    ],
    figure_program: "def draw(seed): ...",
  } as unknown as QuestionDetail;
}

describe("QuestionFigureCopies regenerate", () => {
  beforeEach(() => {
    mutateAsync.mockReset().mockResolvedValue({});
  });

  it("regenerates one copy by ordinal", async () => {
    const user = userEvent.setup();
    const onUpdated = vi.fn();
    render(<QuestionFigureCopies detail={detailWithCopies()} onUpdated={onUpdated} />);

    const buttons = screen.getAllByRole("button", { name: "Regenerate" });
    expect(buttons).toHaveLength(2);
    const second = buttons[1];
    expect(second).toBeDefined();
    await user.click(second as HTMLElement);

    expect(mutateAsync).toHaveBeenCalledWith({ questionId: 7, ordinal: 1 });
    expect(onUpdated).toHaveBeenCalledTimes(1);
  });

  it("shows an error when regenerate fails", async () => {
    mutateAsync.mockRejectedValueOnce(new Error("Seed already used."));
    const user = userEvent.setup();
    render(<QuestionFigureCopies detail={detailWithCopies()} />);

    const first = screen.getAllByRole("button", { name: "Regenerate" })[0];
    expect(first).toBeDefined();
    await user.click(first as HTMLElement);
    expect(await screen.findByRole("alert")).toHaveTextContent("Seed already used.");
  });
});
