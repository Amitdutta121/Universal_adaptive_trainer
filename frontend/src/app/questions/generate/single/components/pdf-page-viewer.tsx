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

import { Maximize2, Minimize2 } from "lucide-react";
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
/** Zoom bounds and step for the viewer's own resize control. */
const MIN_ZOOM = 0.5;
const MAX_ZOOM = 2.5;
const ZOOM_STEP = 0.1;
/**
 * Slack subtracted from the scroll area before fitting a whole page into its
 * height — the container's own padding plus a little breathing room, mirroring
 * pdf.js's VERTICAL_PADDING for its "Page Fit" zoom mode.
 */
const FIT_PAGE_V_PADDING = 40;

type FitMode = "width" | "page";

/** Round to one decimal so repeated steps don't drift (0.30000000004). */
function clampZoom(value: number): number {
  return Math.min(MAX_ZOOM, Math.max(MIN_ZOOM, Math.round(value * 10) / 10));
}

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
  const rootRef = useRef<HTMLDivElement>(null);
  const containerRef = useRef<HTMLDivElement>(null);
  const slotRefs = useRef<Map<number, HTMLDivElement>>(new Map());
  const visibilityRef = useRef<Map<number, number>>(new Map());

  const [numPages, setNumPages] = useState<number | null>(null);
  const [currentPage, setCurrentPage] = useState(1);
  const [isFullscreen, setIsFullscreen] = useState(false);
  // Aspect ratio of a page (height / width), measured once from the first page
  // that actually renders — used to size the placeholder slots at any zoom.
  const [pageAspect, setPageAspect] = useState<number | null>(null);
  const [containerWidth, setContainerWidth] = useState(560);
  const [containerHeight, setContainerHeight] = useState(720);
  const [zoom, setZoom] = useState(1);
  const [fitMode, setFitMode] = useState<FitMode>("page");
  const [loadError, setLoadError] = useState(false);

  // The base width a page is rendered at, before the user's zoom multiplier.
  // "width" fills the column (a tall page just scrolls — the browser/pdf.js
  // "fit width" / "automatic" default). "page" also caps it so a whole page
  // fits the visible height, so shrinking the pane shrinks the page — pdf.js's
  // "Page Fit": scale = min(fitByWidth, fitByHeight).
  const fitByHeight =
    (containerHeight - FIT_PAGE_V_PADDING) / (pageAspect ?? FALLBACK_ASPECT);
  const basePageWidth =
    fitMode === "page" ? Math.min(containerWidth, fitByHeight) : containerWidth;
  const pageWidth = Math.max(240, Math.round(basePageWidth * zoom));

  const sourceUrl = useMemo(() => `${API_BASE_URL}/api/books/${bookId}/source`, [bookId]);
  const anchors = useMemo(() => buildAnchors(rows), [rows]);
  const selectedRow = useMemo(
    () => rows.find((row) => row.sectionId === selectedSectionId) ?? null,
    [rows, selectedSectionId],
  );

  // Native fullscreen on the viewer's own root — no route change, and the
  // ResizeObserver below re-fits the pages to the new size on its own. The
  // listener keeps our state honest when the user leaves fullscreen with Esc
  // or the browser chrome rather than our button.
  useEffect(() => {
    const sync = () => setIsFullscreen(document.fullscreenElement === rootRef.current);
    document.addEventListener("fullscreenchange", sync);
    return () => document.removeEventListener("fullscreenchange", sync);
  }, []);

  const toggleFullscreen = () => {
    if (document.fullscreenElement) {
      void document.exitFullscreen();
    } else {
      void rootRef.current?.requestFullscreen?.();
    }
  };

  // The scroll area's own box drives page sizing — width always, height too in
  // "page" fit mode. Tracking both means a drag on the pane's resize handle
  // re-fits the pages live, the same way a real PDF viewer reflows on window
  // resize.
  useEffect(() => {
    const node = containerRef.current;
    if (!node) return;
    const observer = new ResizeObserver((entries) => {
      const box = entries[0]?.contentRect;
      if (!box) return;
      if (box.width) setContainerWidth(Math.max(280, Math.floor(box.width - 32)));
      if (box.height) setContainerHeight(Math.max(240, Math.floor(box.height)));
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
  const estimatedHeight = pageWidth * (pageAspect ?? FALLBACK_ASPECT);

  return (
    <div
      ref={rootRef}
      className={`flex h-full min-h-0 flex-col overflow-hidden border bg-background ${
        isFullscreen ? "" : "rounded-[1rem]"
      }`}
    >
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

        <div className="flex items-center gap-1">
          <button
            type="button"
            disabled={zoom <= MIN_ZOOM}
            onClick={() => setZoom((z) => clampZoom(z - ZOOM_STEP))}
            className="rounded-md border px-2 py-1 text-xs leading-none disabled:cursor-not-allowed disabled:opacity-40"
            title="Zoom out"
          >
            −
          </button>
          <button
            type="button"
            onClick={() => setZoom(1)}
            className="min-w-[3rem] rounded-md border px-2 py-1 text-center font-mono text-[0.7rem] text-muted-foreground tabular-nums hover:bg-muted"
            title={fitMode === "page" ? "Reset to fit page" : "Reset to fit width"}
          >
            {Math.round(zoom * 100)}%
          </button>
          <button
            type="button"
            disabled={zoom >= MAX_ZOOM}
            onClick={() => setZoom((z) => clampZoom(z + ZOOM_STEP))}
            className="rounded-md border px-2 py-1 text-xs leading-none disabled:cursor-not-allowed disabled:opacity-40"
            title="Zoom in"
          >
            +
          </button>
          <button
            type="button"
            onClick={() => {
              setZoom(1);
              setFitMode((mode) => (mode === "width" ? "page" : "width"));
            }}
            className="rounded-md border px-2 py-1 text-muted-foreground text-xs leading-none hover:bg-muted"
            title={
              fitMode === "width"
                ? "Fitting page width — switch to fit whole page"
                : "Fitting whole page — switch to fit width"
            }
          >
            {fitMode === "width" ? "Fit width" : "Fit page"}
          </button>
        </div>

        <div className="flex min-w-0 items-center gap-2">
          <span className="hidden truncate font-mono text-[0.67rem] text-muted-foreground sm:block">
            {selectedRow?.locationLabel ?? selectedRow?.title ?? "scroll to browse"}
          </span>
          <button
            type="button"
            onClick={toggleFullscreen}
            className="shrink-0 rounded-md border p-1 text-muted-foreground hover:bg-muted"
            title={isFullscreen ? "Exit full screen (Esc)" : "Full screen"}
            aria-label={isFullscreen ? "Exit full screen" : "Full screen"}
          >
            {isFullscreen ? <Minimize2 className="size-3.5" /> : <Maximize2 className="size-3.5" />}
          </button>
        </div>
      </div>

      <div ref={containerRef} className="flex-1 space-y-3 overflow-auto bg-muted/20 p-4">
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
                        if (!pageAspect && loaded.height) {
                          setPageAspect(loaded.height / pageWidth);
                        }
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
