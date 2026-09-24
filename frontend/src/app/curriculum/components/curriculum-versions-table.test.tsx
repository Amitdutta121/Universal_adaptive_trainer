import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";
import { TooltipProvider } from "@/components/ui/tooltip";
import type { CurriculumVersionSummary } from "@/lib/api/types";
import { CurriculumVersionsTable } from "./curriculum-versions-table";

const version = (id: number, label: string): CurriculumVersionSummary =>
  ({
    id,
    label,
    status: "approved",
    generated_by: "taxonomy-upload",
    source_book_ids: [],
    created_at: "2026-09-23T10:00:00Z",
    approved_at: "2026-09-23T10:00:00Z",
    topic_count: 3,
    subtopic_count: 6,
  }) as CurriculumVersionSummary;

function setup(selectedId: number | null = null) {
  const handlers = {
    onSelect: vi.fn(),
    onActivate: vi.fn(),
    onEdit: vi.fn(),
    onDelete: vi.fn(),
  };
  render(
    <TooltipProvider>
      <CurriculumVersionsTable
        versions={[version(2, "Newer"), version(1, "Older")]}
        approvedVersionId={2}
        activatingVersionId={null}
        selectedId={selectedId}
        openingId={null}
        {...handlers}
      />
    </TooltipProvider>,
  );
  return handlers;
}

describe("CurriculumVersionsTable", () => {
  it("lists each taxonomy with its size and its standing", () => {
    setup();

    const rows = screen.getAllByRole("row");
    expect(rows).toHaveLength(2);
    expect(within(rows[0] as HTMLElement).getByText("Newer")).toBeInTheDocument();
    expect(within(rows[0] as HTMLElement).getByText(/3 topics · 6 subtopics/)).toBeInTheDocument();
    expect(within(rows[0] as HTMLElement).getByText("active")).toBeInTheDocument();
    expect(within(rows[1] as HTMLElement).getByText("replaced")).toBeInTheDocument();
  });

  it("selects a row on click and on Enter or Space", async () => {
    const user = userEvent.setup();
    const { onSelect } = setup();

    await user.click(screen.getByText("Older"));
    expect(onSelect).toHaveBeenLastCalledWith(expect.objectContaining({ id: 1 }));

    const newer = screen.getAllByRole("row")[0] as HTMLElement;
    newer.focus();
    await user.keyboard("{Enter}");
    expect(onSelect).toHaveBeenLastCalledWith(expect.objectContaining({ id: 2 }));
    await user.keyboard(" ");
    expect(onSelect).toHaveBeenCalledTimes(3);
  });

  it("marks the open taxonomy as selected", () => {
    setup(1);

    const [newer, older] = screen.getAllByRole("row");
    expect(newer).toHaveAttribute("aria-selected", "false");
    expect(older).toHaveAttribute("aria-selected", "true");
  });

  it("opens a row's actions without also selecting the row", async () => {
    const user = userEvent.setup();
    const { onSelect, onEdit } = setup();

    await user.click(screen.getByRole("button", { name: "Actions for Older" }));
    await user.click(await screen.findByRole("menuitem", { name: "Rename" }));

    expect(onEdit).toHaveBeenCalledWith(expect.objectContaining({ id: 1 }));
    expect(onSelect).not.toHaveBeenCalled();
  });

  it("offers Make active only for a replaced taxonomy, and a link to the full record", async () => {
    const user = userEvent.setup();
    const { onActivate } = setup();

    await user.click(screen.getByRole("button", { name: "Actions for Newer" }));
    expect(await screen.findByRole("menuitem", { name: "Make active" })).toHaveAttribute(
      "aria-disabled",
      "true",
    );
    expect(screen.getByRole("menuitem", { name: "View details" })).toHaveAttribute(
      "href",
      "/curriculum/versions/2",
    );
    expect(onActivate).not.toHaveBeenCalled();
  });
});
