import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { DraftWithAiDialog } from "./draft-with-ai-dialog";

const draft = vi.fn();

vi.mock("@/lib/use-course", () => ({ useCourseId: () => 1 }));
vi.mock("@/lib/api/queries", () => ({
  useCourse: () => ({ data: { name: "CS 135", description: "Intro to programming." } }),
  useDraftTaxonomy: () => ({ mutateAsync: draft, isPending: false, error: null }),
}));

function open() {
  render(<DraftWithAiDialog open onOpenChange={() => {}} onDrafted={() => {}} />);
}

describe("DraftWithAiDialog counts", () => {
  beforeEach(() => {
    draft.mockReset();
    draft.mockResolvedValue({ drafted_by: "x", analysis: "", document: { label: "", topics: [] } });
  });

  it("sends the professor's own numbers", async () => {
    const user = userEvent.setup();
    open();
    const subtopics = screen.getByLabelText("Subtopics in total");
    await user.clear(subtopics);
    await user.type(subtopics, "12");
    await user.type(screen.getByLabelText(/Topics/), "4");
    await user.click(screen.getByRole("button", { name: /Draft taxonomy/ }));
    expect(draft).toHaveBeenCalledWith(
      expect.objectContaining({ subtopic_count: 12, topic_count: 4 }),
    );
  });

  it("fills the subtopic count from a preset and clears the topic count", async () => {
    const user = userEvent.setup();
    open();
    await user.type(screen.getByLabelText(/Topics/), "3");
    await user.click(screen.getByRole("button", { name: "Fewer, broader · 15" }));
    expect(screen.getByLabelText("Subtopics in total")).toHaveValue(15);
    expect(screen.getByLabelText(/Topics/)).toHaveValue(null);
  });

  it("lets the AI decide when both are empty, and refuses impossible numbers", async () => {
    const user = userEvent.setup();
    open();
    const subtopics = screen.getByLabelText("Subtopics in total");
    const submit = screen.getByRole("button", { name: /Draft taxonomy/ });

    await user.clear(subtopics);
    await user.type(screen.getByLabelText(/Topics/), "5");
    await user.type(subtopics, "3");
    expect(screen.getByText("Every topic needs at least one subtopic.")).toBeInTheDocument();
    expect(submit).toBeDisabled();

    await user.clear(subtopics);
    await user.clear(screen.getByLabelText(/Topics/));
    await user.click(submit);
    expect(draft).toHaveBeenCalledWith(
      expect.objectContaining({ subtopic_count: null, topic_count: null, size: "standard" }),
    );
  });
});
