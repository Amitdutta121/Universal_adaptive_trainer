"use client";

/**
 * Which decks the student has finished (their faded check answered right), kept in localStorage.
 * Storage can throw or be empty (private window, blocked site data), so every access is guarded
 * and the page works without it.
 *
 * TODO(real): completion would be a mastery signal saved to the student's profile, not a browser flag.
 */

import { useCallback, useEffect, useState } from "react";

export const DONE_KEY = "tutorials-deck:done:v1";

export function useDoneTopics() {
  const [done, setDone] = useState<string[]>([]);

  useEffect(() => {
    try {
      const parsed: unknown = JSON.parse(window.localStorage.getItem(DONE_KEY) ?? "[]");
      if (Array.isArray(parsed)) {
        setDone(parsed.filter((item): item is string => typeof item === "string"));
      }
    } catch {
      // No storage: start with nothing done.
    }
  }, []);

  const markDone = useCallback(
    (id: string) => {
      if (done.includes(id)) return;
      const next = [...done, id];
      setDone(next);
      try {
        window.localStorage.setItem(DONE_KEY, JSON.stringify(next));
      } catch {
        // Still shown as done for this visit.
      }
    },
    [done],
  );

  return { done, markDone };
}
