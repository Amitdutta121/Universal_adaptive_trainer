/** Test bootstrap: DOM matchers, and a clean DOM between tests. */

import "@testing-library/jest-dom/vitest";
import { cleanup } from "@testing-library/react";
import { afterEach } from "vitest";

afterEach(() => {
  cleanup();
});

/**
 * jsdom has no `ResizeObserver`, and Radix popovers (tooltips, selects) measure themselves with one
 * the moment they open. Without this a tooltip that happens to open during a test throws inside
 * React and unmounts the whole tree, which made tests that hover a button pass or fail by timing.
 */
class ResizeObserverStub {
  observe() {}
  unobserve() {}
  disconnect() {}
}
globalThis.ResizeObserver ??= ResizeObserverStub;
