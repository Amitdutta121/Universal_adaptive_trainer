import { describe, expect, it } from "vitest";
import { explainRefusal } from "./taxonomy-refusal";

const doc = {
  topics: [
    { name: "Lists", subtopics: [{ name: "Indexing" }, { name: "Slicing" }] },
    { name: "Sets", subtopics: [{ name: "Union" }] },
  ],
};

describe("explainRefusal", () => {
  it("counts from one and names the topic, dropping the parser's wording", () => {
    expect(explainRefusal("topics.1: Value error, duplicate subtopic name 'union'", doc)).toEqual([
      "Topic 2 (“Sets”): duplicate subtopic name 'union'",
    ]);
  });

  it("locates a field of a subtopic", () => {
    expect(
      explainRefusal("topics.0.subtopics.1.name: String should have at most 300 characters", doc),
    ).toEqual([
      "The name of subtopic 2 (“Slicing”) of topic 1 (“Lists”): this is too long (at most 300 characters)",
    ]);
  });

  it("still counts from one when the document is not to hand, and just leaves the names out", () => {
    expect(explainRefusal("topics.2.subtopics.0.name: Field required")).toEqual([
      "The name of subtopic 1 of topic 3: this is required",
    ]);
  });

  it("names the label, the topic list and an unknown field in plain words", () => {
    expect(explainRefusal("label: String should have at least 1 character")).toEqual([
      "The taxonomy name: this cannot be empty",
    ]);
    expect(
      explainRefusal("topics: List should have at least 1 item after validation, not 0"),
    ).toEqual(["The list of topics: this needs at least one entry"]);
  });

  it("keeps every problem, in order", () => {
    const out = explainRefusal(
      "topics.0.name: Field required; topics.1: Value error, duplicate subtopic name 'a'",
      doc,
    );
    expect(out).toHaveLength(2);
    expect(out[0]).toMatch(/^The name of topic 1/);
    expect(out[1]).toMatch(/^Topic 2/);
  });

  it("passes through a path it does not understand, and text with no path at all", () => {
    // An unknown field is reported by the server as an extra key; the sentence is not improved, and not hidden.
    expect(explainRefusal("topics.0.colour: Extra inputs are not permitted", doc)).toEqual([
      "topics.0.colour: Extra inputs are not permitted",
    ]);
    expect(explainRefusal("something.odd: a thing went wrong")).toEqual([
      "something.odd: a thing went wrong",
    ]);
    expect(explainRefusal("Unsupported taxonomy schema_version.")).toEqual([
      "Unsupported taxonomy schema_version.",
    ]);
  });
});
