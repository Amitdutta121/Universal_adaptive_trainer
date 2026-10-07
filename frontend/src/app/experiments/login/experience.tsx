"use client";

/**
 * The version switcher. The chosen version is in the URL (`?v=a|b|c|d`), so a link to one version
 * can be shared and a reload keeps it.
 */

import { parseAsStringLiteral, useQueryState } from "nuqs";
import { VersionA, VersionB, VersionC, VersionD } from "./versions";

const VERSIONS = ["a", "b", "c", "d"] as const;
type VersionKey = (typeof VERSIONS)[number];

const VERSION_LABEL: Record<VersionKey, { name: string; idea: string }> = {
  a: { name: "A · Split", idea: "Form on the left, a real screenshot of the review queue on the right." },
  b: { name: "B · Two doors", idea: "Instructors sign in, students enter a class code, side by side." },
  c: { name: "C · Account picker", idea: "Remembered accounts first, password second." },
  d: { name: "D · Quiet", idea: "No card; university SSO and an email link above the password form." },
};

export function LoginExperience() {
  const [version, setVersion] = useQueryState("v", parseAsStringLiteral(VERSIONS).withDefault("a"));

  return (
    <div className="min-h-screen bg-background">
      <header className="sticky top-0 z-20 border-b bg-background/95 backdrop-blur">
        <div className="flex w-full flex-wrap items-center gap-3 px-6 py-3">
          <div className="mr-auto">
            <div className="font-semibold text-sm">Login — prototype</div>
            <div className="text-muted-foreground text-xs">
              {VERSION_LABEL[version].idea} Password <span className="font-mono">wrong</span> shows the
              error.
            </div>
          </div>
          <div role="tablist" aria-label="Prototype version" className="flex rounded-lg border p-0.5">
            {VERSIONS.map((key) => (
              <button
                key={key}
                type="button"
                role="tab"
                aria-selected={version === key}
                onClick={() => void setVersion(key)}
                className="rounded-md px-3 py-1.5 font-medium text-xs transition-colors aria-selected:bg-primary aria-selected:text-primary-foreground"
              >
                {VERSION_LABEL[key].name}
              </button>
            ))}
          </div>
        </div>
      </header>
      {version === "a" ? <VersionA /> : version === "b" ? <VersionB /> : version === "c" ? <VersionC /> : <VersionD />}
    </div>
  );
}
