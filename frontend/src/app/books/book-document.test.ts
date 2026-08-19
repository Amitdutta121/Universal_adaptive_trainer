/**
 * The two decisions a book upload makes that a taxonomy upload does not.
 *
 * The structural JSON checks these used to cover are shared now, and tested in
 * `lib/json-document.test.ts`. What is left here is the pair of book-specific
 * choices: the filename a pasted book travels under, and `title` being an
 * override whose blank value the endpoint documents as "use the document's own".
 */

import { describe, expect, it } from "vitest";
import { PASTED_BOOK_FILENAME, titleOverride } from "./book-document";

describe("PASTED_BOOK_FILENAME", () => {
  it("ends in the only extension the book import accepts", () => {
    expect(PASTED_BOOK_FILENAME.endsWith(".json")).toBe(true);
  });
});

describe("titleOverride", () => {
  it("omits a blank title so the document's own is used", () => {
    expect(titleOverride("   ")).toBeUndefined();
    expect(titleOverride(" Think Python ")).toBe("Think Python");
  });
});
