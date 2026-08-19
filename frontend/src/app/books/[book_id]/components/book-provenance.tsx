"use client";

/**
 * Where this book came from.
 *
 * The uploaded document is retained so an import is reproducible from its exact
 * input; this is the trail back to it. Provenance fields are shown only when the
 * document stated them — nothing here is inferred from a filename.
 */

import type { BookSummary } from "@/lib/api/types";
import { formatTimestamp } from "@/lib/display";
import { formatFileSize } from "../../book-display";

function Row({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div className="flex flex-wrap justify-between gap-2 border-b py-2 text-sm last:border-b-0">
      <dt className="text-muted-foreground">{label}</dt>
      <dd className="text-right">{children}</dd>
    </div>
  );
}

export function BookProvenance({ book }: { book: BookSummary }) {
  return (
    <dl>
      <Row label="Uploaded document">
        <code className="font-mono text-xs">{book.original_filename}</code>
      </Row>
      {book.source_filename ? (
        <Row label="Produced from">
          <code className="font-mono text-xs">{book.source_filename}</code>
        </Row>
      ) : null}
      {book.producer ? (
        <Row label="Produced by">
          <code className="font-mono text-xs">{book.producer}</code>
        </Row>
      ) : null}
      <Row label="Format">
        <code className="font-mono text-xs">{book.source_format}</code>
      </Row>
      <Row label="Size">{formatFileSize(book.file_size_bytes)}</Row>
      <Row label="Uploaded">{formatTimestamp(book.created_at)}</Row>
      {book.imported_at ? <Row label="Imported">{formatTimestamp(book.imported_at)}</Row> : null}
    </dl>
  );
}
