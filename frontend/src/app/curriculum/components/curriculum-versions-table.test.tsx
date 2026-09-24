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

function setup(openingId: number | null = null) {
  const handlers = {
    onOpen: vi.fn(),
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
        openingId={openingId}
        {...handlers}
      />
    </TooltipProvider>,
  );
  return handlers;
}

const bodyRows = () => screen.getAllByRole("row").slice(1);

describe("CurriculumVersionsTable", () => {
  it("shows every column of a taxonomy's record, with its standing", () => {
    setup();

    expect(screen.getAllByRole("columnheader").map((h) => h.textContent)).toEqual([
      "#",
      "Name",
      "Status",
      "Topics",
      "Subtopics",
      "Source",
      "Created",
      "Made active",
      "",
    ]);
    const [newer, older] = bodyRows() as [HTMLElement, HTMLElement];
    expect(within(newer).getByText("Newer")).toBeInTheDocument();
    expect(within(newer).getByText("active")).toBeInTheDocument();
    expect(within(newer).getByText("3")).toBeInTheDocument();
    expect(within(newer).getByText("6")).toBeInTheDocument();
    expect(within(older).getByText("replaced")).toBeInTheDocument();
  });

  it("opens a row on click and on Enter or Space", async () => {
    const user = userEvent.setup();
    const { onOpen } = setup();

    await user.click(screen.getByText("Older"));
    expect(onOpen).toHaveBeenLastCalledWith(expect.objectContaining({ id: 1 }));

    (bodyRows()[0] as HTMLElement).focus();
    await user.keyboard("{Enter}");
    expect(onOpen).toHaveBeenLastCalledWith(expect.objectContaining({ id: 2 }));
    await user.keyboard(" ");
    expect(onOpen).toHaveBeenCalledTimes(3);
  });

  it("opens a row from its Preview button, once", async () => {
    const user = userEvent.setup();
    const { onOpen } = setup();

    await user.click(screen.getByRole("button", { name: "Preview Older" }));

    expect(onOpen).toHaveBeenCalledTimes(1);
    expect(onOpen).toHaveBeenCalledWith(expect.objectContaining({ id: 1 }));
  });

  it("dims the row whose taxonomy is still being fetched", () => {
    setup(1);

    const [newer, older] = bodyRows();
    expect(older).toHaveClass("opacity-60");
    expect(newer).not.toHaveClass("opacity-60");
  });

  it("opens a row's actions without also opening the row", async () => {
    const user = userEvent.setup();
    const { onOpen, onEdit } = setup();

    await user.click(screen.getByRole("button", { name: "Actions for Older" }));
    await user.click(await screen.findByRole("menuitem", { name: "Rename" }));

    expect(onEdit).toHaveBeenCalledWith(expect.objectContaining({ id: 1 }));
    expect(onOpen).not.toHaveBeenCalled();
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
