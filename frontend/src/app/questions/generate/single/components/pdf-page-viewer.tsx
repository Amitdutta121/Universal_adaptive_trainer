"use client";

/**
 * The book's retained PDF, rendered as one continuous scroll.
 *
 * Every page gets a slot in the scroll container the moment the document's
 * page count is known, so the scrollbar always represents the whole book —
 * but only a window of pages around whatever is currently in view is ever
 * rendered as a real `<Page>`; the rest sit as plain placeholder divs sized to
 * the measured page height. That keeps a 100+ page book from putting a
 * hundred live canvases in the DOM at once.
 *
 * The component owns the mapping from "page currently in view" to "which
 * outline row that page belongs to" (`rows`, by `startPage`/`endPage`), and
 * reports it upward so the outline can auto-follow the scroll. Selecting a
 * row from the outline is the same relationship in reverse: this component
 * jumps its scroll position to that row's first page whenever
 * `selectedSectionId` changes to a value it didn't already imply.
 */

import { useEffect, useMemo, useRef, useState } from "react";
import { Document, Page, pdfjs } from "react-pdf";
import { API_BASE_URL } from "@/lib/env";
import type { SheetRow } from "../../spec-sheet-types";

pdfjs.GlobalWorkerOptions.workerSrc = new URL(
  "pdfjs-dist/build/pdf.worker.min.mjs",
  import.meta.url,
).toString();

/** Pages to keep actually rendered on either side of the current page. */
const RENDER_RADIUS = 3;
/** Guess used for a page's height before any page has been measured. */
const FALLBACK_ASPECT = 1.3;

interface PageAnchor {
  sectionId: number;
  startPage: number;
}

/** Sorted ascending by `startPage`; rows with no known page are left out. */
function buildAnchors(rows: readonly SheetRow[]): PageAnchor[] {
  return rows
    .filter((row): row is SheetRow & { startPage: number } => row.startPage !== null)
    .map((row) => ({ sectionId: row.sectionId, startPage: row.startPage }))
    .sort((a, b) => a.startPage - b.startPage);
}

/**
 * Which row's range the given page falls into.
 *
 * When two chunks start on the same page (a short section sharing a page with
 * the one after it, which real books do), the first of them in reading order
 * wins — `anchors` is sorted by `startPage` and a stable sort keeps same-page
 * anchors in that original order, so taking the first anchor at the highest
 * startPage `<= page` picks the chunk whose heading actually opens the page,
 * not whichever happened to sort last.
 */
function sectionForPage(anchors: readonly PageAnchor[], page: number): number | null {
  let found: number | null = null;
  let bestStartPage = Number.NEGATIVE_INFINITY;
  for (const anchor of anchors) {
    if (anchor.startPage > page) break;
    if (anchor.startPage > bestStartPage) {
      bestStartPage = anchor.startPage;
      found = anchor.sectionId;
    }
  }
  return found ?? anchors[0]?.sectionId ?? null;
}

export function PdfPageViewer({
  bookId,
  rows,
  selectedSectionId,
  onVisibleSectionChange,
}: {
  bookId: number;
  rows: readonly SheetRow[];
  selectedSectionId: number | null;
  onVisibleSectionChange: (sectionId: number) => void;
}) {
  const containerRef = useRef<HTMLDivElement>(null);
  const slotRefs = useRef<Map<number, HTMLDivElement>>(new Map());
  const visibilityRef = useRef<Map<number, number>>(new Map());

  const [numPages, setNumPages] = useState<number | null>(null);
  const [currentPage, setCurrentPage] = useState(1);
  const [pageHeight, setPageHeight] = useState<number | null>(null);
  const [pageWidth, setPageWidth] = useState(560);
  const [loadError, setLoadError] = useState(false);

  const sourceUrl = useMemo(() => `${API_BASE_URL}/api/books/${bookId}/source`, [bookId]);
  const anchors = useMemo(() => buildAnchors(rows), [rows]);
  const selectedRow = useMemo(
    () => rows.find((row) => row.sectionId === selectedSectionId) ?? null,
    [rows, selectedSectionId],
  );

  // Page width tracks the column's own width, not a fixed guess.
  useEffect(() => {
    const node = containerRef.current;
    if (!node) return;
    const observer = new ResizeObserver((entries) => {
      const width = entries[0]?.contentRect.width;
      if (width) setPageWidth(Math.max(280, Math.floor(width - 32)));
    });
    observer.observe(node);
    return () => observer.disconnect();
  }, []);

  // One observer for every page slot: whichever is most visible becomes "current".
  // IntersectionObserver only reports elements that crossed a threshold since the
  // last check, not every observed element — so each page's last-known ratio is
  // kept in `visibilityRef` and the "most visible" page is recomputed from that
  // whole map every time, rather than from just the entries in this callback.
  useEffect(() => {
    if (!numPages) return;
    const root = containerRef.current;
    visibilityRef.current.clear();

    const observer = new IntersectionObserver(
      (entries) => {
        for (const entry of entries) {
          const page = Number((entry.target as HTMLElement).dataset.pageNumber);
          if (!page) continue;
          visibilityRef.current.set(page, entry.intersectionRatio);
        }
        let bestPage: number | null = null;
        let bestRatio = 0;
        for (const [page, ratio] of visibilityRef.current) {
          if (ratio > bestRatio || (ratio === bestRatio && bestPage !== null && page < bestPage)) {
            bestRatio = ratio;
            bestPage = page;
          }
        }
        if (bestPage !== null && bestRatio > 0) setCurrentPage(bestPage);
      },
      { root, threshold: [0, 0.25, 0.5, 0.75, 1] },
    );

    for (const el of slotRefs.current.values()) observer.observe(el);
    return () => observer.disconnect();
  }, [numPages]);

  // The page in view implies a section; tell the outline, but only on change.
  // selectedSectionId and onVisibleSectionChange are read, not watched — this
  // fires on scroll, and should not also fire when the outline's own selection
  // changes (that would loop).
  // biome-ignore lint/correctness/useExhaustiveDependencies: see comment above
  useEffect(() => {
    const implied = sectionForPage(anchors, currentPage);
    if (implied !== null && implied !== selectedSectionId) onVisibleSectionChange(implied);
  }, [currentPage, anchors]);

  const scrollToPage = (page: number, behavior: ScrollBehavior = "smooth") => {
    slotRefs.current.get(page)?.scrollIntoView({ behavior, block: "start" });
  };

  // A row picked from the outline jumps the scroll here, instantly (a smooth
  // scroll across dozens of pages would fire the observer for every page it
  // passes, fighting this same effect). selectedRow is derived from
  // selectedSectionId — re-running because selectedRow's identity changed (e.g.
  // rows reloaded) would re-jump the scroll with nothing the user did.
  // `numPages` is a real dependency, not an incidental one: this effect runs on
  // mount before the document has loaded, when no slot refs exist yet and the
  // jump would silently no-op, so it must run again once slots exist.
  // biome-ignore lint/correctness/useExhaustiveDependencies: see comment above
  useEffect(() => {
    if (selectedRow?.startPage) scrollToPage(selectedRow.startPage, "auto");
  }, [selectedSectionId, numPages]);

  const slots = numPages ? Array.from({ length: numPages }, (_, index) => index + 1) : [];
  const estimatedHeight = pageHeight ?? pageWidth * FALLBACK_ASPECT;

  return (
    <div className="flex h-full min-h-0 flex-col overflow-hidden rounded-[1rem] border">
      <div className="flex items-center justify-between border-b bg-muted/40 px-3 py-2">
        <div className="flex items-center gap-2">
          <button
            type="button"
            disabled={currentPage <= 1}
            onClick={() => scrollToPage(currentPage - 1)}
            className="rounded-md border px-2 py-1 text-xs disabled:cursor-not-allowed disabled:opacity-40"
          >
            Prev
          </button>
          <span className="font-mono text-[0.75rem] text-muted-foreground tabular-nums">
            Page {currentPage}
            {numPages ? ` of ${numPages}` : ""}
          </span>
          <button
            type="button"
            disabled={numPages !== null && currentPage >= numPages}
            onClick={() => scrollToPage(currentPage + 1)}
            className="rounded-md border px-2 py-1 text-xs disabled:cursor-not-allowed disabled:opacity-40"
          >
            Next
          </button>
        </div>
        <span className="truncate font-mono text-[0.67rem] text-muted-foreground">
          {selectedRow?.locationLabel ?? selectedRow?.title ?? "scroll to browse"}
        </span>
      </div>

      <div ref={containerRef} className="flex-1 space-y-3 overflow-y-auto bg-muted/20 p-4">
        {loadError ? (
          <p className="max-w-sm py-8 text-center text-muted-foreground text-sm">
            The original PDF isn't available for this book — it may have been imported from a
            structured document rather than a PDF file.
          </p>
        ) : (
          <Document
            file={sourceUrl}
            onLoadSuccess={({ numPages: total }) => setNumPages(total)}
            onLoadError={() => setLoadError(true)}
            loading={<p className="py-8 text-muted-foreground text-sm">Loading document…</p>}
          >
            {slots.map((page) => {
              const inWindow = Math.abs(page - currentPage) <= RENDER_RADIUS;
              const inSelectedRange =
                selectedRow?.startPage != null &&
                page >= selectedRow.startPage &&
                page <= (selectedRow.endPage ?? selectedRow.startPage);
              return (
                <div
                  key={page}
                  data-page-number={page}
                  ref={(el) => {
                    if (el) slotRefs.current.set(page, el);
                    else slotRefs.current.delete(page);
                  }}
                  className={`relative mx-auto flex justify-center ${
                    inSelectedRange
                      ? "ring-2 ring-primary/60 ring-offset-2 ring-offset-background"
                      : ""
                  }`}
                  // A minHeight (not a conditional height) even for an in-window,
                  // real `<Page>`: react-pdf's canvas has no size until it finishes
                  // loading, and without a floor here the slot would momentarily
                  // collapse the instant a placeholder becomes a real page — shrinking
                  // total scroll height under a fixed scrollTop and silently landing
                  // the viewport on a different page than the one just jumped to.
                  style={{ minHeight: estimatedHeight, width: pageWidth }}
                >
                  {inWindow ? (
                    <Page
                      pageNumber={page}
                      width={pageWidth}
                      renderTextLayer={false}
                      renderAnnotationLayer={false}
                      onRenderSuccess={(loaded) => {
                        if (!pageHeight) setPageHeight(loaded.height);
                      }}
                    />
                  ) : null}
                  {inSelectedRange && page === selectedRow?.startPage ? (
                    <span className="absolute -top-2.5 left-1 rounded bg-primary px-1.5 py-0.5 font-mono text-[0.6rem] text-primary-foreground">
                      {selectedRow.title}
                    </span>
                  ) : null}
                </div>
              );
            })}
          </Document>
        )}
      </div>
    </div>
  );
}
