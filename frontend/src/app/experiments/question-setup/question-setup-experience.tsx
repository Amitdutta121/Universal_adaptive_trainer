"use client";

/**
 * The domain switcher. The chosen course is in the URL (`?d=python|physics|biology`); each
 * domain gets a fresh wizard, so switching starts that course from step 1.
 */

import { parseAsStringLiteral, useQueryState } from "nuqs";
import { BIOLOGY } from "./mock-biology";
import { PHYSICS } from "./mock-physics";
import { PYTHON } from "./mock-python";
import type { Domain } from "./mock-types";
import { Wizard } from "./wizard";

const DOMAINS = ["python", "physics", "biology"] as const;
type DomainKey = (typeof DOMAINS)[number];

const DOMAIN_BY_KEY: Record<DomainKey, Domain> = {
  python: PYTHON,
  physics: PHYSICS,
  biology: BIOLOGY,
};

export function QuestionSetupExperience() {
  const [key, setKey] = useQueryState("d", parseAsStringLiteral(DOMAINS).withDefault("python"));
  const domain = DOMAIN_BY_KEY[key];

  return (
    <div className="min-h-screen bg-background">
      <header className="sticky top-0 z-20 border-b bg-background/95 backdrop-blur">
        <div className="mx-auto flex w-full max-w-6xl flex-wrap items-center gap-3 px-6 py-3">
          <div className="mr-auto">
            <div className="font-semibold text-sm">Question setup — prototype</div>
            <div className="text-muted-foreground text-xs">Mock data, no AI calls. Switching course starts over.</div>
          </div>
          <div role="tablist" aria-label="Course" className="flex rounded-lg border p-0.5">
            {DOMAINS.map((entry) => (
              <button
                key={entry}
                type="button"
                role="tab"
                aria-selected={key === entry}
                onClick={() => void setKey(entry)}
                className="rounded-md px-3 py-1.5 font-medium text-xs transition-colors aria-selected:bg-primary aria-selected:text-primary-foreground"
              >
                {DOMAIN_BY_KEY[entry].subjectLabel}
              </button>
            ))}
          </div>
        </div>
      </header>
      <main className="mx-auto w-full max-w-6xl px-6 py-6">
        <Wizard key={domain.id} domain={domain} />
      </main>
    </div>
  );
}
