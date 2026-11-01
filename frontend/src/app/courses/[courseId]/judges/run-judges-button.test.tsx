import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { NuqsTestingAdapter } from "nuqs/adapters/testing";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { TooltipProvider } from "@/components/ui/tooltip";
import type { JudgeRerunPreview } from "@/lib/api/types";

vi.mock("sonner", () => ({ toast: { success: vi.fn(), error: vi.fn() } }));

let preview: JudgeRerunPreview;
const mutateAsync = vi.fn();
vi.mock("@/lib/api/queries", () => ({
  useJudgeRerunPreview: () => ({ isPending: false, data: preview }),
  useRunJudges: () => ({ mutateAsync, isPending: false }),
}));

import { RunJudgesButton } from "./run-judges-button";

function renderButton() {
  render(
    <NuqsTestingAdapter>
      <TooltipProvider>
        <RunJudgesButton />
      </TooltipProvider>
    </NuqsTestingAdapter>,
  );
  return screen.getByRole("button", { name: /Run judges/ });
}

beforeEach(() => {
  mutateAsync.mockReset();
  mutateAsync.mockResolvedValue({ run: { run_id: "r1" }, submitted: 42 });
  preview = { enabled: true, disabled_reason: null, eligible: 42, active_run_id: null };
});

describe("RunJudgesButton", () => {
  it("asks first, naming how many questions it will send, then submits", async () => {
    await userEvent.click(renderButton());

    expect(screen.getByRole("heading", { name: "Re-judge 42 questions?" })).toBeInTheDocument();
    expect(mutateAsync).not.toHaveBeenCalled();

    await userEvent.click(screen.getByRole("button", { name: "Run judges on 42" }));
    expect(mutateAsync).toHaveBeenCalledOnce();
  });

  it("stays off with the reason when re-runs are switched off", async () => {
    preview = {
      enabled: false,
      disabled_reason: "Judge re-runs are switched off.",
      eligible: 42,
      active_run_id: null,
    };
    const user = userEvent.setup();
    const button = renderButton();

    expect(button).toHaveAttribute("aria-disabled", "true");
    await user.hover(button);
    expect((await screen.findAllByText("Judge re-runs are switched off.")).length).toBeGreaterThan(
      0,
    );
    await user.click(button);
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
  });

  it("stays off while a run is already in progress", async () => {
    preview = { ...preview, active_run_id: "r0" };
    const button = renderButton();

    await userEvent.click(button);
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
  });
});
