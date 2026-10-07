import { describe, expect, it } from "vitest";
import type { Job } from "@/lib/api/types";
import { KIND_LABEL, linkLabel, outcomeText } from "./job-display";

function bookImport(result: Job["result"]): Job {
  return {
    id: "job-3",
    kind: "book_import",
    title: "Import book · textbook.pdf",
    status: "done",
    done: 1,
    total: 1,
    result,
    link: "/books/4",
    created_at: "2026-10-07T00:00:00Z",
  } as Job;
}

describe("book import jobs", () => {
  it("say which book was imported, and whether it is partial", () => {
    const book = { id: 4, title: "Python Programming", status: "imported" };
    expect(outcomeText(bookImport({ book } as Job["result"]))).toBe(
      "Imported “Python Programming”",
    );
    expect(outcomeText(bookImport({ book: { ...book, status: "partial" } } as Job["result"]))).toBe(
      "Imported “Python Programming” (partial)",
    );
  });

  it("are labelled and linked as a book", () => {
    expect(KIND_LABEL.book_import).toBe("Book import");
    expect(linkLabel(bookImport(null))).toBe("Open book");
  });
});
