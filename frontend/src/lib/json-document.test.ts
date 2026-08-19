/**
 * What the console checks before an upload, and what it leaves to the backend.
 *
 * The line these tests pin is the important one: unparseable text is caught here
 * because the professor can fix it without a round trip, and everything about a
 * *document contract* — required fields, unknown keys, section text, duplicate
 * taxonomy names — is refused by `app/ingestion/schema.py` and
 * `app/curriculum/taxonomy_schema.py` and tested there. A rule that appears in
 * both places is a rule that can disagree with itself.
 */

import { describe, expect, it } from "vitest";
import { exceedsUploadLimit, fileFromPastedJson, jsonProblem } from "./json-document";

describe("fileFromPastedJson", () => {
  it("uploads pasted text under the name it is given", () => {
    const file = fileFromPastedJson('{"schema_version": "1"}', "pasted-book.json");
    expect(file.name).toBe("pasted-book.json");
    expect(file.type).toBe("application/json");
  });

  it("keeps the text byte for byte", async () => {
    const text = '{\n  "text": "    indented listing"\n}';
    expect(await fileFromPastedJson(text, "pasted-book.json").text()).toBe(text);
  });
});

describe("jsonProblem", () => {
  it("accepts a JSON object without inspecting its fields", () => {
    // Nonsense as a book document, and still this client's business to send:
    // refusing it here would be a second, divergent copy of the schema.
    expect(jsonProblem('{"not": "a book"}')).toBeNull();
  });

  it("asks for a document when nothing was supplied", () => {
    expect(jsonProblem("   ")).toMatch(/Paste the document/);
  });

  it("names a markdown fence, the most common way a chat reply arrives", () => {
    expect(jsonProblem('```json\n{"schema_version": "1"}\n```')).toMatch(/code fence/);
  });

  it("reports unparseable text with the parser's own reason", () => {
    expect(jsonProblem('{"title": "Broken",}')).toMatch(/not valid JSON/);
  });

  it("refuses a top-level array or scalar", () => {
    expect(jsonProblem("[1, 2]")).toMatch(/must be a JSON object/);
    expect(jsonProblem('"a string"')).toMatch(/must be a JSON object/);
  });

  it("names the document it was given, so a shared check stays specific", () => {
    expect(jsonProblem("[1, 2]", "taxonomy document")).toMatch(
      /A taxonomy document must be a JSON object/,
    );
    expect(jsonProblem("[1, 2]", "book document")).toMatch(/A book document must be a JSON object/);
  });
});

describe("exceedsUploadLimit", () => {
  it("mirrors the limit the backend enforces", () => {
    expect(exceedsUploadLimit(5 * 1024 * 1024, 100)).toBe(false);
    expect(exceedsUploadLimit(101 * 1024 * 1024, 100)).toBe(true);
    expect(exceedsUploadLimit(100 * 1024 * 1024, 100)).toBe(false);
  });
});
