/**
 * Keep an unsaved taxonomy across a reload, a rejected save, or a closed tab.
 *
 * A professor typing thirty subtopics should not lose them to a refresh, and a
 * rejected save must leave what they typed exactly where it is. This is a
 * per-browser convenience, not a record: nothing here reaches the server, and it
 * never has to be present for the screen to work. Every access is guarded because
 * storage can be blocked, full, or cleared (private windows, site-data settings),
 * and none of those may break editing.
 *
 * The undo history is deliberately not stored: it is a session's worth of
 * "put that back", and restoring it after a reload would offer to undo things the
 * professor no longer remembers doing.
 */

import type { Draft } from "./taxonomy-draft";

const KEY = "adaptive-trainer:taxonomy-draft:v1";

export interface StoredDraft {
  savedAt: string;
  draft: Draft;
}

const isText = (value: unknown): value is string => typeof value === "string";
const isRecord = (value: unknown): value is Record<string, unknown> =>
  typeof value === "object" && value !== null && !Array.isArray(value);

/**
 * A stored draft, or `null` when the text is not one this version wrote. Storage
 * outlives the code that wrote it, so a malformed or older shape is dropped rather
 * than trusted into the editor.
 */
export function parseStoredDraft(raw: string | null): StoredDraft | null {
  if (!raw) return null;
  try {
    const value: unknown = JSON.parse(raw);
    if (!isRecord(value) || !isText(value.savedAt) || !isRecord(value.draft)) return null;
    const { label, topics } = value.draft;
    if (!isText(label) || !Array.isArray(topics)) return null;

    for (const topic of topics) {
      if (
        !isRecord(topic) ||
        !isText(topic.id) ||
        !isText(topic.name) ||
        !isText(topic.description) ||
        !Array.isArray(topic.subtopics)
      ) {
        return null;
      }
      for (const subtopic of topic.subtopics) {
        if (
          !isRecord(subtopic) ||
          !isText(subtopic.id) ||
          !isText(subtopic.name) ||
          !isText(subtopic.description)
        ) {
          return null;
        }
      }
    }
    return { savedAt: value.savedAt, draft: value.draft as unknown as Draft };
  } catch {
    return null;
  }
}

export function loadDraft(): StoredDraft | null {
  try {
    return parseStoredDraft(window.localStorage.getItem(KEY));
  } catch {
    return null;
  }
}

export function saveDraft(draft: Draft): void {
  try {
    const stored: StoredDraft = { savedAt: new Date().toISOString(), draft };
    window.localStorage.setItem(KEY, JSON.stringify(stored));
  } catch {
    // Storage is unavailable or full. Editing carries on; the draft just is not kept.
  }
}

export function clearDraft(): void {
  try {
    window.localStorage.removeItem(KEY);
  } catch {
    // Nothing to clear if storage is unavailable.
  }
}
