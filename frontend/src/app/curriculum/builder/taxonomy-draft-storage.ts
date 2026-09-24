/**
 * Keep unsaved taxonomies across a reload, a rejected save, or a closed tab.
 *
 * A professor typing thirty subtopics should not lose them to a refresh, and a
 * rejected save must leave what they typed exactly where it is. Each taxonomy has
 * its own slot (a new one, or a copy of a particular saved one), so opening or
 * previewing something else never touches, replaces or has to ask about work left
 * unsaved somewhere else; only editing that same taxonomy again overwrites its slot. This is a
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

/** One slot per taxonomy. */
const KEY = "adaptive-trainer:taxonomy-drafts:v2";
/** The single slot this replaced; read once and moved, so nobody's unsaved work is orphaned. */
const LEGACY_KEY = "adaptive-trainer:taxonomy-draft:v1";

/** The saved taxonomy a draft was opened from, if it was opened from one. */
export interface DraftOrigin {
  id: number;
  label: string;
}

export interface StoredDraft {
  savedAt: string;
  draft: Draft;
  origin: DraftOrigin | null;
}

/** A stored draft together with the slot it lives in. */
export interface SavedDraft extends StoredDraft {
  key: string;
}

/** Which slot a draft belongs in: a copy of a particular saved taxonomy, or a new one. */
export const draftKey = (origin: DraftOrigin | null): string => (origin ? `v${origin.id}` : "new");

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
    return checkStoredDraft(JSON.parse(raw));
  } catch {
    return null;
  }
}

/** The saved row a draft row came from is a number when there is one; anything else is not ours. */
function isOptionalId(value: unknown): boolean {
  return value === undefined || (typeof value === "number" && Number.isInteger(value));
}

function checkStoredDraft(value: unknown): StoredDraft | null {
  try {
    if (!isRecord(value) || !isText(value.savedAt) || !isRecord(value.draft)) return null;
    const { label, topics } = value.draft;
    if (!isText(label) || !Array.isArray(topics)) return null;

    for (const topic of topics) {
      if (
        !isRecord(topic) ||
        !isText(topic.id) ||
        !isText(topic.name) ||
        !isText(topic.description) ||
        !isOptionalId(topic.serverId) ||
        !Array.isArray(topic.subtopics)
      ) {
        return null;
      }
      for (const subtopic of topic.subtopics) {
        if (
          !isRecord(subtopic) ||
          !isText(subtopic.id) ||
          !isText(subtopic.name) ||
          !isText(subtopic.description) ||
          !isOptionalId(subtopic.serverId)
        ) {
          return null;
        }
      }
    }
    const { origin } = value;
    const validOrigin =
      isRecord(origin) && typeof origin.id === "number" && isText(origin.label)
        ? { id: origin.id, label: origin.label }
        : null;
    return { savedAt: value.savedAt, draft: value.draft as unknown as Draft, origin: validOrigin };
  } catch {
    return null;
  }
}

function readAll(): Record<string, StoredDraft> {
  const all: Record<string, StoredDraft> = {};
  try {
    const raw = window.localStorage.getItem(KEY);
    const value: unknown = raw ? JSON.parse(raw) : null;
    if (isRecord(value)) {
      for (const [key, entry] of Object.entries(value)) {
        const parsed = checkStoredDraft(entry);
        if (parsed) all[key] = parsed;
      }
    }
  } catch {
    // Unreadable or blocked storage is the same as having nothing stored.
  }
  return all;
}

function writeAll(all: Record<string, StoredDraft>): void {
  try {
    if (Object.keys(all).length === 0) window.localStorage.removeItem(KEY);
    else window.localStorage.setItem(KEY, JSON.stringify(all));
  } catch {
    // Storage is unavailable or full. Editing carries on; the draft just is not kept.
  }
}

/** Every unsaved taxonomy kept in this browser, most recently edited first. */
export function loadDrafts(): SavedDraft[] {
  try {
    const legacy = parseStoredDraft(window.localStorage.getItem(LEGACY_KEY));
    if (legacy) {
      const all = readAll();
      const key = draftKey(legacy.origin);
      if (!all[key]) all[key] = legacy;
      writeAll(all);
      window.localStorage.removeItem(LEGACY_KEY);
    }
  } catch {
    // Nothing to migrate if storage cannot be read.
  }
  return Object.entries(readAll())
    .map(([key, stored]) => ({ ...stored, key }))
    .sort((a, b) => b.savedAt.localeCompare(a.savedAt));
}

/** Keep `draft` in the slot for `origin`, replacing only what was already kept for that taxonomy. */
export function saveDraft(draft: Draft, origin: DraftOrigin | null = null): void {
  const all = readAll();
  all[draftKey(origin)] = { savedAt: new Date().toISOString(), draft, origin };
  writeAll(all);
}

/** Forget the draft kept for `origin`, and no other. */
export function clearDraft(origin: DraftOrigin | null = null): void {
  const all = readAll();
  delete all[draftKey(origin)];
  writeAll(all);
}
