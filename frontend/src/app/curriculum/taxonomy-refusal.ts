/**
 * Turn the server's refusal of a taxonomy document into sentences a professor can act on.
 *
 * The backend validates the whole document and reports *where* each problem is as a path
 * (`topics.2.subtopics.1.name: Value error, duplicate subtopic name 'x'`), counting from zero.
 * That is exact for a program and opaque for a person: "topics.2" is the third topic, and
 * "Value error" says nothing. This puts positions in human counting, names the topic or
 * subtopic when the document that was sent is at hand, and drops the parser's vocabulary.
 *
 * It only rewrites how a problem is *described*. Which problems exist is still decided by the
 * backend alone; anything this does not recognise is passed through unchanged, so a message it
 * cannot improve is never hidden or invented.
 */

/** The parts of a document that carry names, as sent to the server. */
export interface NamedDocument {
  topics?: { name?: unknown; subtopics?: { name?: unknown }[] }[];
}

const named = (value: unknown): string =>
  typeof value === "string" && value.trim() ? ` (“${value.trim()}”)` : "";

/** Where in the document a path points, in words. */
function describeLocation(path: string, doc: NamedDocument | null | undefined): string | null {
  const parts = path.split(".");
  const [first, topicIndex, second, subtopicIndex, field] = parts;
  if (first === "label" && parts.length === 1) return "The taxonomy name";
  if (first === "schema_version" && parts.length === 1) return "The schema version";
  if (first !== "topics") return null;
  if (parts.length === 1) return "The list of topics";

  const t = Number(topicIndex);
  if (!Number.isInteger(t)) return null;
  const topic = `topic ${t + 1}${named(doc?.topics?.[t]?.name)}`;
  if (second === undefined) return `Topic ${t + 1}${named(doc?.topics?.[t]?.name)}`;
  if (second === "name") return `The name of ${topic}`;
  if (second === "description") return `The description of ${topic}`;
  if (second !== "subtopics") return null;
  if (subtopicIndex === undefined) return `The subtopics of ${topic}`;

  const s = Number(subtopicIndex);
  if (!Number.isInteger(s)) return null;
  const subtopic = `subtopic ${s + 1}${named(doc?.topics?.[t]?.subtopics?.[s]?.name)} of ${topic}`;
  if (field === undefined) return `${subtopic[0]?.toUpperCase()}${subtopic.slice(1)}`;
  if (field === "name") return `The name of ${subtopic}`;
  if (field === "description") return `The description of ${subtopic}`;
  return null;
}

/** The parser's wording, said plainly. Unknown wording is returned as it came. */
function describeProblem(message: string): string {
  const text = message.replace(/^Value error, /, "").trim();
  if (text === "Field required") return "this is required";
  if (text === "Extra inputs are not permitted")
    return "this is not something a taxonomy can contain";
  const tooLong = text.match(/^String should have at most (\d+) characters?$/);
  if (tooLong) return `this is too long (at most ${tooLong[1]} characters)`;
  if (/^String should have at least 1 character/.test(text)) return "this cannot be empty";
  if (/^List should have at least 1 item/.test(text)) return "this needs at least one entry";
  return text;
}

/** One sentence per problem the server reported, in the order it reported them. */
export function explainRefusal(detail: string, doc?: NamedDocument | null): string[] {
  return detail
    .split("; ")
    .map((part) => part.trim())
    .filter(Boolean)
    .map((part) => {
      const at = part.indexOf(": ");
      if (at < 0) return part;
      const where = describeLocation(part.slice(0, at), doc);
      if (!where) return part;
      return `${where}: ${describeProblem(part.slice(at + 2))}`;
    });
}
