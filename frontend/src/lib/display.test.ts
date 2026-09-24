import { describe, expect, it } from "vitest";
import { formatTimestamp } from "./display";

describe("formatTimestamp", () => {
  const shown = (iso: string) =>
    new Date(iso).toLocaleString(undefined, { dateStyle: "medium", timeStyle: "short" });

  it("reads a time with no zone marker as UTC, which is what the API sends", () => {
    // Without the fix this was parsed as local time and printed hours off in any zone but UTC.
    expect(formatTimestamp("2026-09-24T01:41:00")).toBe(shown("2026-09-24T01:41:00Z"));
  });

  it("leaves a time that already carries a zone alone", () => {
    expect(formatTimestamp("2026-09-24T01:41:00Z")).toBe(shown("2026-09-24T01:41:00Z"));
    expect(formatTimestamp("2026-09-24T01:41:00+02:00")).toBe(shown("2026-09-24T01:41:00+02:00"));
  });

  it("shows a dash for something that is not a time", () => {
    expect(formatTimestamp("not a date")).toBe("—");
  });
});
