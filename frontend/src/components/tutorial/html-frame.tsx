"use client";

import { useEffect, useRef, useState } from "react";

/**
 * Runs an html tutorial block (Phase 5, Task 22).
 *
 * Two walls, both always on:
 * - `sandbox="allow-scripts"` without `allow-same-origin`: the frame is an opaque origin, so its
 *   scripts cannot read this page, its cookies or its storage, and cannot navigate the top page.
 * - A Content-Security-Policy injected first into the document: no fetch, XHR, WebSocket, image,
 *   font or frame from the network, no form posts. Inline script and style only.
 *
 * The frame reports its height with `postMessage({type: "tutorial-block-resize", height})`;
 * messages from any other window are ignored.
 */

export const HTML_BLOCK_CSP = [
  "default-src 'none'",
  "script-src 'unsafe-inline'",
  "style-src 'unsafe-inline'",
  "img-src data:",
  "font-src data:",
  "connect-src 'none'",
  "frame-src 'none'",
  "form-action 'none'",
  "base-uri 'none'",
].join("; ");

export const HTML_BLOCK_SANDBOX = "allow-scripts";

const CSP_META = `<meta http-equiv="Content-Security-Policy" content="${HTML_BLOCK_CSP}">`;
const MIN_HEIGHT = 80;
const MAX_HEIGHT = 2000;

/** The document the frame runs: the CSP meta before anything else the block contains. */
export function sandboxedDocument(html: string): string {
  const doctype = /^\s*<!doctype[^>]*>/i.exec(html);
  if (doctype) {
    return `${doctype[0]}${CSP_META}${html.slice(doctype[0].length)}`;
  }
  return `${CSP_META}${html}`;
}

export function HtmlFrame({ html, title }: { html: string; title: string }) {
  const frame = useRef<HTMLIFrameElement>(null);
  const [height, setHeight] = useState(320);

  useEffect(() => {
    function onMessage(event: MessageEvent) {
      if (!frame.current || event.source !== frame.current.contentWindow) return;
      const data = event.data as { type?: unknown; height?: unknown } | null;
      if (data?.type !== "tutorial-block-resize" || typeof data.height !== "number") return;
      setHeight(Math.min(MAX_HEIGHT, Math.max(MIN_HEIGHT, Math.ceil(data.height))));
    }
    window.addEventListener("message", onMessage);
    return () => window.removeEventListener("message", onMessage);
  }, []);

  return (
    <iframe
      ref={frame}
      title={title || "Interactive tutorial"}
      sandbox={HTML_BLOCK_SANDBOX}
      srcDoc={sandboxedDocument(html)}
      referrerPolicy="no-referrer"
      className="w-full rounded-md border bg-white"
      style={{ height }}
    />
  );
}
