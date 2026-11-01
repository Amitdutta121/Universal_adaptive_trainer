import { describe, expect, it } from "vitest";
import { contentTypeOf } from "./book-display";

describe("contentTypeOf", () => {
  it("labels a YouTube upload a video", () => {
    expect(contentTypeOf({ source_format: "youtube" })).toBe("video");
  });

  it("labels every uploaded file a book", () => {
    for (const format of ["book_pdf", "book_docx", "book_pptx", "book_json"] as const) {
      expect(contentTypeOf({ source_format: format })).toBe("book");
    }
  });
});
