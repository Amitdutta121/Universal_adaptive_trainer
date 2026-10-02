/**
 * The taxonomy a professor is building by hand, and the edits they can make to it.
 *
 * Pure data and pure functions, so the screen holds only what the browser owns
 * (selection, search text, focus) and every rule below is testable without a DOM.
 *
 * This is deliberately *not* a validator. `app/curriculum/taxonomy_schema.py` owns
 * what a valid taxonomy is — duplicate-name rules included — and a second copy of
 * those rules here would drift from it. The one thing checked locally is search,
 * which is a view over the draft, not a claim about it.
 *
 * Removal returns the removed item along with the new draft so the caller can put
 * it back exactly where it was: undo is a first-class operation here, not an
 * afterthought bolted onto a delete.
 */

export interface DraftSubtopic {
  id: string;
  /** The saved row this one is, when it came from a saved taxonomy. Absent for a new one. */
  serverId?: number;
  name: string;
  description: string;
}

export interface DraftTopic {
  id: string;
  /** The saved row this one is, when it came from a saved taxonomy. Absent for a new one. */
  serverId?: number;
  name: string;
  description: string;
  subtopics: DraftSubtopic[];
}

export interface Draft {
  label: string;
  topics: DraftTopic[];
}

/** A subtopic is selected within its topic; `subtopicId: null` selects the topic itself. */
export interface Selection {
  topicId: string;
  subtopicId: string | null;
}

export type Removal =
  | { id: string; kind: "topic"; index: number; topic: DraftTopic }
  | { id: string; kind: "subtopic"; topicId: string; index: number; subtopic: DraftSubtopic };

/** One topic as the tree shows it under the current search. */
export interface TreeTopic {
  topic: DraftTopic;
  subtopics: DraftSubtopic[];
}

/**
 * Client-side keys for rows that have no database id yet. Random rather than a
 * counter: a draft restored from storage carries the ids it was saved with, and a
 * counter that restarts at zero on every page load would reuse them.
 */
export function newId(prefix: string): string {
  return `${prefix}-${crypto.randomUUID()}`;
}

function matches(item: { name: string; description: string }, needle: string): boolean {
  return (
    item.name.toLowerCase().includes(needle) || item.description.toLowerCase().includes(needle)
  );
}

/**
 * What the tree shows for a search.
 *
 * A topic that matches on its own keeps all its subtopics, for context. A topic
 * shown only because a subtopic matched lists just the matching subtopics.
 */
export function filterTree(topics: readonly DraftTopic[], query: string): TreeTopic[] {
  const needle = query.trim().toLowerCase();
  if (!needle) return topics.map((topic) => ({ topic, subtopics: topic.subtopics }));

  const shown: TreeTopic[] = [];
  for (const topic of topics) {
    const matchingSubtopics = topic.subtopics.filter((subtopic) => matches(subtopic, needle));
    if (matches(topic, needle)) shown.push({ topic, subtopics: topic.subtopics });
    else if (matchingSubtopics.length > 0) shown.push({ topic, subtopics: matchingSubtopics });
  }
  return shown;
}

/** Items that matched the search themselves, not rows shown only for context. */
export function countMatches(topics: readonly DraftTopic[], query: string): number {
  const needle = query.trim().toLowerCase();
  if (!needle) return 0;
  return topics.reduce(
    (total, topic) =>
      total +
      (matches(topic, needle) ? 1 : 0) +
      topic.subtopics.filter((subtopic) => matches(subtopic, needle)).length,
    0,
  );
}

/** True when the row matched only through its description, so the tree can say why it is listed. */
export function matchedByDescriptionOnly(
  item: { name: string; description: string },
  query: string,
): boolean {
  const needle = query.trim().toLowerCase();
  return (
    needle !== "" &&
    !item.name.toLowerCase().includes(needle) &&
    item.description.toLowerCase().includes(needle)
  );
}

export function countSubtopics(draft: Draft): number {
  return draft.topics.reduce((total, topic) => total + topic.subtopics.length, 0);
}

export function removeTopic(draft: Draft, topicId: string): { draft: Draft; removal: Removal } {
  const index = draft.topics.findIndex((topic) => topic.id === topicId);
  const topic = draft.topics[index];
  if (!topic) throw new Error(`No topic ${topicId}`);
  return {
    draft: { ...draft, topics: draft.topics.filter((t) => t.id !== topicId) },
    removal: { id: newId("removal"), kind: "topic", index, topic },
  };
}

export function removeSubtopic(
  draft: Draft,
  topicId: string,
  subtopicId: string,
): { draft: Draft; removal: Removal } {
  const owner = draft.topics.find((topic) => topic.id === topicId);
  const index = owner?.subtopics.findIndex((subtopic) => subtopic.id === subtopicId) ?? -1;
  const subtopic = owner?.subtopics[index];
  if (!owner || !subtopic) throw new Error(`No subtopic ${subtopicId} in ${topicId}`);
  return {
    draft: {
      ...draft,
      topics: draft.topics.map((topic) =>
        topic.id === topicId
          ? { ...topic, subtopics: topic.subtopics.filter((s) => s.id !== subtopicId) }
          : topic,
      ),
    },
    removal: { id: newId("removal"), kind: "subtopic", topicId, index, subtopic },
  };
}

/**
 * Put a removed item back where it was. Positions are clamped, so a removal
 * undone after other edits lands as near as it can rather than failing. A
 * subtopic whose topic is gone is dropped; undoing in the order things were
 * removed (what the stack does) brings the topic back first.
 */
export function restoreRemoval(draft: Draft, removal: Removal): Draft {
  if (removal.kind === "topic") {
    const topics = [...draft.topics];
    topics.splice(Math.min(removal.index, topics.length), 0, removal.topic);
    return { ...draft, topics };
  }
  return {
    ...draft,
    topics: draft.topics.map((topic) => {
      if (topic.id !== removal.topicId) return topic;
      const subtopics = [...topic.subtopics];
      subtopics.splice(Math.min(removal.index, subtopics.length), 0, removal.subtopic);
      return { ...topic, subtopics };
    }),
  };
}

export function describeRemoval(removal: Removal): string {
  if (removal.kind === "subtopic") {
    return `Removed subtopic “${removal.subtopic.name || "Untitled"}”`;
  }
  const count = removal.topic.subtopics.length;
  const also = count > 0 ? ` and its ${count} ${count === 1 ? "subtopic" : "subtopics"}` : "";
  return `Removed topic “${removal.topic.name || "Untitled"}”${also}`;
}

/** Swap an item with its neighbour. A move off either end is a no-op, so callers need not check. */
function moved<T>(items: readonly T[], index: number, delta: -1 | 1): T[] {
  const target = index + delta;
  if (index < 0 || target < 0 || target >= items.length) return [...items];
  const next = [...items];
  const from = next[index] as T;
  next[index] = next[target] as T;
  next[target] = from;
  return next;
}

export function moveTopic(draft: Draft, topicId: string, delta: -1 | 1): Draft {
  const index = draft.topics.findIndex((topic) => topic.id === topicId);
  return { ...draft, topics: moved(draft.topics, index, delta) };
}

export function moveSubtopic(
  draft: Draft,
  topicId: string,
  subtopicId: string,
  delta: -1 | 1,
): Draft {
  return {
    ...draft,
    topics: draft.topics.map((topic) =>
      topic.id === topicId
        ? {
            ...topic,
            subtopics: moved(
              topic.subtopics,
              topic.subtopics.findIndex((subtopic) => subtopic.id === subtopicId),
              delta,
            ),
          }
        : topic,
    ),
  };
}

export function emptyDraft(): Draft {
  return { label: "", topics: [] };
}

/** The shape of a saved version's tree that a draft is made from (the API's `TopicOut`, structurally). */
export interface VersionTopic {
  id?: number;
  name: string;
  description?: string | null;
  subtopics: { id?: number; name: string; description?: string | null }[];
}

/**
 * A draft holding a saved taxonomy, to edit and save back to it or as a new version.
 *
 * A draft row's own `id` is a client-side key and is always fresh. The saved row it came from is
 * remembered separately as `serverId`, which is what lets a save tell the server "this is the
 * same row, renamed" rather than "delete that and add this". Missing descriptions become empty
 * text.
 */
export function draftFromVersion(label: string, topics: readonly VersionTopic[]): Draft {
  return {
    label,
    topics: topics.map((topic) => ({
      id: newId("topic"),
      ...(topic.id === undefined ? {} : { serverId: topic.id }),
      name: topic.name,
      description: topic.description ?? "",
      subtopics: topic.subtopics.map((subtopic) => ({
        id: newId("sub"),
        ...(subtopic.id === undefined ? {} : { serverId: subtopic.id }),
        name: subtopic.name,
        description: subtopic.description ?? "",
      })),
    })),
  };
}

/** The name a copy starts with. A copy of a copy is not "X (copy) (copy)". */
export function copyLabel(label: string): string {
  return /\(copy\)\s*$/i.test(label) ? label : `${label} (copy)`;
}

/**
 * A comparable fingerprint of a draft, so "has this changed since it was loaded" is a string
 * comparison. Editing something and then editing it back is not a change.
 */
export function draftSignature(draft: Draft): string {
  return JSON.stringify(draft);
}

/** Whether there is anything worth keeping: an empty draft is not saved, and restoring one would be noise. */
export function isDraftEmpty(draft: Draft): boolean {
  return draft.label.trim() === "" && draft.topics.length === 0;
}

/**
 * The taxonomy document the backend validates (`app/curriculum/taxonomy_schema.py`).
 *
 * `schemaVersion` is the one the backend's guide reports, not a constant here, so
 * a schema bump cannot leave this sending the old version. Blank descriptions are
 * sent as empty strings, which is what the schema defaults them to.
 */
export function toTaxonomyDocument(draft: Draft, schemaVersion: string) {
  return {
    schema_version: schemaVersion,
    label: draft.label.trim(),
    topics: draft.topics.map((topic) => ({
      name: topic.name.trim(),
      description: topic.description.trim(),
      subtopics: topic.subtopics.map((subtopic) => ({
        name: subtopic.name.trim(),
        description: subtopic.description.trim(),
      })),
    })),
  };
}

/**
 * The edit that brings a saved taxonomy to this draft (`PUT .../tree`): the whole tree, each row
 * carrying the saved id it came from, or none if it is new. Names are trimmed as the document's
 * are; what makes a tree valid is still the server's to say.
 */
export function toTreeUpdate(draft: Draft) {
  return {
    label: draft.label.trim(),
    topics: draft.topics.map((topic) => ({
      id: topic.serverId ?? null,
      name: topic.name.trim(),
      description: topic.description.trim(),
      subtopics: topic.subtopics.map((subtopic) => ({
        id: subtopic.serverId ?? null,
        name: subtopic.name.trim(),
        description: subtopic.description.trim(),
      })),
    })),
  };
}

export interface DraftProblem {
  message: string;
  /** Where to send the professor: the label field, or the item that needs attention. */
  at: "label" | Selection;
}

/**
 * The first thing that would make the backend refuse this draft *for being
 * unfinished*: a blank name, or no topics. Deliberately nothing else. Duplicate
 * names, length limits and every other rule are the backend's to enforce, and its
 * refusal is shown as it words it.
 */
export function findProblem(draft: Draft): DraftProblem | null {
  if (draft.label.trim() === "") {
    return { message: "Give this taxonomy a name.", at: "label" };
  }
  if (draft.topics.length === 0) {
    return { message: "Add at least one topic.", at: "label" };
  }
  for (const topic of draft.topics) {
    if (topic.name.trim() === "") {
      return {
        message: "A topic has no name.",
        at: { topicId: topic.id, subtopicId: null },
      };
    }
    if (topic.subtopics.length === 0) {
      return {
        message: `“${topic.name.trim()}” has no subtopics. Every topic needs at least one.`,
        at: { topicId: topic.id, subtopicId: null },
      };
    }
    for (const subtopic of topic.subtopics) {
      if (subtopic.name.trim() === "") {
        return {
          message: `A subtopic of “${topic.name.trim()}” has no name.`,
          at: { topicId: topic.id, subtopicId: subtopic.id },
        };
      }
    }
  }
  return null;
}

/** The bounds `GET /curriculum/document-guide` publishes, by the field they apply to. */
export interface FieldLimits {
  label?: number;
  topicName?: number;
  topicDescription?: number;
  subtopicName?: number;
  subtopicDescription?: number;
}

const LIMIT_PATHS: Record<keyof FieldLimits, string> = {
  label: "label",
  topicName: "topics[].name",
  topicDescription: "topics[].description",
  subtopicName: "topics[].subtopics[].name",
  subtopicDescription: "topics[].subtopics[].description",
};

/**
 * Read the limits out of the guide's field reference. Until the guide has loaded
 * there are none, and the inputs are simply unbounded: a limit typed here as a
 * fallback would be a second copy of a number the backend owns.
 */
export function limitsFromGuide(
  fields: readonly { path: string; max_length: number | null }[] | undefined,
): FieldLimits {
  const limits: FieldLimits = {};
  for (const key of Object.keys(LIMIT_PATHS) as (keyof FieldLimits)[]) {
    const max = fields?.find((field) => field.path === LIMIT_PATHS[key])?.max_length;
    if (typeof max === "number") limits[key] = max;
  }
  return limits;
}
