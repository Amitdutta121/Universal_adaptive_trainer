/**
 * The Adaptive Trainer mark: an open book whose right page lifts off the spine as a rising
 * arrow, i.e. practice that grows out of your own course material. Drawn in `currentColor` on a
 * 24px grid so it sits in the same places a lucide icon would. `app/icon.svg` is the same
 * glyph on the teal tile; keep the two paths in sync.
 */

import type * as React from "react";

export function LogoGlyph({ className, ...props }: React.ComponentProps<"svg">) {
  return (
    <svg
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth={2}
      strokeLinecap="round"
      strokeLinejoin="round"
      aria-hidden="true"
      className={className}
      {...props}
    >
      <path d="M12 20c-2.6-1.6-5.6-2.1-9-1.4V7c3.4-.7 6.4-.2 9 1.4V20c2.6-1.6 5.6-2.1 9-1.4V13" />
      <path d="M12 8.4c2.4-1.9 5-3.2 8.6-4" />
      <path d="M17.3 3.1l3.4 1.3-1.4 3.2" />
    </svg>
  );
}
