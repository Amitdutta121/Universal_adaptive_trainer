/** A book upload's `title` is an override whose blank value means "use the file's own". */

import { describe, expect, it } from "vitest";
import { titleOverride } from "./book-document";

describe("titleOverride", () => {
  it("omits a blank title so the document's own is used", () => {
    expect(titleOverride("   ")).toBeUndefined();
    expect(titleOverride(" Think Python ")).toBe("Think Python");
  });
});
