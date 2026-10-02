"use client";

/**
 * A value that settles before it is used.
 *
 * The spec sheet is priced by the API on every change. Without this, holding down
 * a stepper would send one request per click; with it, the sheet is priced once
 * the professor stops adjusting it.
 */

import { useEffect, useState } from "react";

export function useDebouncedValue<T>(value: T, delayMs = 300): T {
  const [settled, setSettled] = useState(value);

  useEffect(() => {
    const timer = setTimeout(() => setSettled(value), delayMs);
    return () => clearTimeout(timer);
  }, [value, delayMs]);

  return settled;
}
