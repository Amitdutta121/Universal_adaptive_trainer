/** A small, fixed draft for tests. Not imported by any screen. */

import type { Draft } from "./taxonomy-draft";

export function sampleDraft(): Draft {
  return {
    label: "Introductory Python",
    topics: [
      {
        id: "topic-a",
        name: "Variables",
        description: "Creating names, assigning values, and understanding types.",
        subtopics: [
          {
            id: "sub-a1",
            name: "Assignment and rebinding",
            description: "Using = to bind a name to a value and reassign it later.",
          },
          {
            id: "sub-a2",
            name: "Basic types",
            description: "Working with int, float, str, and bool values.",
          },
          { id: "sub-a3", name: "Type conversion", description: "" },
        ],
      },
      {
        id: "topic-b",
        name: "Loops",
        description: "Repeating actions with for and while loops.",
        subtopics: [
          {
            id: "sub-b1",
            name: "for loops over sequences",
            description: "Iterating over strings, lists, and other iterables.",
          },
          {
            id: "sub-b2",
            name: "while loops",
            description: "Repeating while a condition remains true.",
          },
        ],
      },
      {
        id: "topic-c",
        name: "Functions",
        description: "",
        subtopics: [
          { id: "sub-c1", name: "Defining and calling", description: "" },
          { id: "sub-c2", name: "Return values", description: "" },
        ],
      },
      { id: "topic-d", name: "Files", description: "", subtopics: [] },
    ],
  };
}
