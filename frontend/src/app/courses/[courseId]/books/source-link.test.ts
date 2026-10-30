import { describe, expect, it } from "vitest";
import { classifyLink } from "./source-link";

describe("classifyLink", () => {
  it.each([
    "https://www.youtube.com/watch?v=AbCdEfGhIjK",
    "https://youtu.be/AbCdEfGhIjK",
    "youtu.be/AbCdEfGhIjK",
    "https://m.youtube.com/shorts/AbCdEfGhIjK",
  ])("takes %s as YouTube", (text) => {
    expect(classifyLink(text)?.kind).toBe("youtube");
  });

  it.each([
    ["https://vimeo.com/123456", true],
    ["https://example.edu/lectures/week1.mp4", true],
    ["https://example.edu/notes.pdf", false],
  ])("knows %s is another link (video: %s)", (text, video) => {
    expect(classifyLink(text)).toMatchObject({ kind: "other", video });
  });

  it("is nothing for blank text and not a link for words", () => {
    expect(classifyLink("  ")).toBeNull();
    expect(classifyLink("loops in python")?.kind).toBe("not_a_link");
    expect(classifyLink("ftp://example.edu/file")?.kind).toBe("not_a_link");
  });
});
