"use client";

/**
 * The chunk selector, styled as a PDF reader's outline/bookmarks pane.
 *
 * Chapters are collapsible parents, sections are their children — the same
 * chapter/section rows the bulk sheet uses (`SheetRow`/`SheetChapter`), just
 * grouped into a tree instead of a flat table, since only one chunk is picked
 * at a time here.
 */

import { ChevronRight, Search } from "lucide-react";
import { useEffect, useMemo, useRef, useState } from "react";
import { Badge } from "@/components/ui/badge";
import { Input } from "@/components/ui/input";
import type { SheetRow } from "../../spec-sheet-types";
import type { SheetChapter, SheetFilters } from "../../use-sheet-rows";

function FieldLabel({ children }: { children: string }) {
  return (
    <span className="font-mono text-[0.67rem] text-muted-foreground uppercase tracking-[0.16em]">
      {children}
    </span>
  );
}

export function OutlinePanel({
  chapters,
  rows,
  selectedSectionId,
  onSelect,
  search,
  onSearchChange,
  produced,
  onProducedChange,
}: {
  chapters: readonly SheetChapter[];
  rows: readonly SheetRow[];
  selectedSectionId: number | null;
  onSelect: (sectionId: number) => void;
  search: string;
  onSearchChange: (value: string) => void;
  produced: SheetFilters["produced"];
  onProducedChange: (value: SheetFilters["produced"]) => void;
}) {
  const [collapsedChapters, setCollapsedChapters] = useState<ReadonlySet<number>>(new Set());
  const rowRefs = useRef<Map<number, HTMLButtonElement>>(new Map());

  const rowsByChapter = useMemo(() => {
    const map = new Map<number, SheetRow[]>();
    for (const row of rows) {
      const bucket = map.get(row.chapterId);
      if (bucket) bucket.push(row);
      else map.set(row.chapterId, [row]);
    }
    return map;
  }, [rows]);

  const toggleChapter = (chapterId: number) => {
    setCollapsedChapters((prev) => {
      const next = new Set(prev);
      if (next.has(chapterId)) next.delete(chapterId);
      else next.add(chapterId);
      return next;
    });
  };

  const isSearching = search.trim().length > 0;

  // A selection driven by scrolling the PDF (not a click here) may land on a
  // chunk whose chapter is collapsed — reveal it rather than highlighting a
  // row the outline is hiding. `rows` is read, not watched — re-expanding on
  // every rows reload (e.g. a refetch) would fight a chapter the professor
  // just collapsed by hand.
  // biome-ignore lint/correctness/useExhaustiveDependencies: see comment above
  useEffect(() => {
    if (selectedSectionId === null) return;
    const row = rows.find((candidate) => candidate.sectionId === selectedSectionId);
    if (!row) return;
    setCollapsedChapters((prev) => {
      if (!prev.has(row.chapterId)) return prev;
      const next = new Set(prev);
      next.delete(row.chapterId);
      return next;
    });
  }, [selectedSectionId]);

  // Keep the highlighted row in view, however it became selected. Re-checked
  // after `collapsedChapters` changes too, even though it's not read here: an
  // auto-expand from the effect above mounts the row a render later than this.
  // biome-ignore lint/correctness/useExhaustiveDependencies: see comment above
  useEffect(() => {
    if (selectedSectionId === null) return;
    rowRefs.current
      .get(selectedSectionId)
      ?.scrollIntoView({ block: "nearest", behavior: "smooth" });
  }, [selectedSectionId, collapsedChapters]);

  return (
    <div className="flex h-full min-h-[420px] flex-col overflow-hidden rounded-[1rem] border">
      <div className="flex items-center justify-between gap-2 border-b bg-muted/40 px-3 py-2.5">
        <FieldLabel>Outline</FieldLabel>
        <span className="font-mono text-[0.67rem] text-muted-foreground">
          {rows.length} chunk{rows.length === 1 ? "" : "s"}
        </span>
      </div>

      <div className="space-y-2 border-b p-3">
        <div className="relative">
          <Search className="pointer-events-none absolute top-1/2 left-3 size-4 -translate-y-1/2 text-muted-foreground" />
          <Input
            value={search}
            onChange={(event) => onSearchChange(event.target.value)}
            placeholder="Search section..."
            className="h-9 pl-9"
          />
        </div>
        <div className="flex flex-wrap gap-1.5">
          {(
            [
              { value: "any", label: "All" },
              { value: "none", label: "Needs questions" },
            ] as const
          ).map((option) => (
            <button
              key={option.value}
              type="button"
              onClick={() => onProducedChange(option.value)}
              className={
                produced === option.value
                  ? "rounded-full bg-primary px-2.5 py-1 font-medium text-primary-foreground text-xs"
                  : "rounded-full border px-2.5 py-1 text-muted-foreground text-xs hover:bg-muted"
              }
            >
              {option.label}
            </button>
          ))}
        </div>
      </div>

      <div className="min-h-0 flex-1 overflow-y-auto">
        {chapters.length === 0 ? (
          <p className="p-4 text-muted-foreground text-sm">No chunks match this filter.</p>
        ) : (
          chapters.map((chapter) => {
            const sections = rowsByChapter.get(chapter.id) ?? [];
            if (sections.length === 0) return null;
            const expanded = isSearching || !collapsedChapters.has(chapter.id);

            return (
              <div key={chapter.id}>
                <button
                  type="button"
                  onClick={() => toggleChapter(chapter.id)}
                  className="flex w-full items-center gap-2 border-t px-3 py-2 text-left font-semibold text-[0.8rem] hover:bg-muted/50"
                >
                  <ChevronRight
                    className={`size-3.5 shrink-0 text-muted-foreground transition-transform ${expanded ? "rotate-90" : ""}`}
                  />
                  <span className="truncate">{chapter.label}</span>
                  <span className="ml-auto font-mono font-normal text-[0.67rem] text-muted-foreground">
                    {sections.length}
                  </span>
                </button>
                {expanded
                  ? sections.map((row) => {
                      const selected = row.sectionId === selectedSectionId;
                      return (
                        <button
                          key={row.sectionId}
                          ref={(el) => {
                            if (el) rowRefs.current.set(row.sectionId, el);
                            else rowRefs.current.delete(row.sectionId);
                          }}
                          type="button"
                          disabled={!row.selectable}
                          onClick={() => onSelect(row.sectionId)}
                          className={`flex w-full items-center gap-2 border-t py-2 pr-3 pl-8 text-left disabled:cursor-not-allowed disabled:opacity-40 ${
                            selected
                              ? "border-l-[3px] border-l-primary bg-primary/10"
                              : "border-l-[3px] border-l-transparent hover:bg-muted/50"
                          }`}
                        >
                          <span className="min-w-0 flex-1">
                            <span className="block truncate text-[0.8rem]">{row.title}</span>
                            <span className="block truncate text-[0.68rem] text-muted-foreground">
                              {row.locationLabel ?? "unlabelled"} · {row.charCount.toLocaleString()}{" "}
                              chars
                            </span>
                          </span>
                          <Badge
                            variant={row.existingQuestionCount > 0 ? "secondary" : "outline"}
                            className="shrink-0 gap-1 font-mono text-[0.63rem]"
                            title={
                              row.existingQuestionCount > 0
                                ? `${row.existingQuestionCount} question${row.existingQuestionCount === 1 ? "" : "s"} already generated from this chunk`
                                : "No questions generated yet"
                            }
                          >
                            {row.existingQuestionCount > 0 ? (
                              <span className="size-1.5 rounded-full bg-emerald-500" />
                            ) : null}
                            {row.existingQuestionCount}
                          </Badge>
                        </button>
                      );
                    })
                  : null}
              </div>
            );
          })
        )}
      </div>
    </div>
  );
}
