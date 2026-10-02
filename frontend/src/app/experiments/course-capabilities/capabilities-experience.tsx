"use client";

/**
 * The version switcher. The chosen version is in the URL (`?v=a|b|c|d`), so a link to one version
 * can be shared and a reload keeps it. Each version is self-contained and keeps its own state.
 */

import { parseAsStringLiteral, useQueryState } from "nuqs";
import { VersionA } from "./version-a/version-a";
import { VersionB } from "./version-b/version-b";
import { VersionC } from "./version-c/version-c";
import { VersionD } from "./version-d/version-d";

const VERSIONS = ["a", "b", "c", "d"] as const;
type VersionKey = (typeof VERSIONS)[number];

const VERSION_LABEL: Record<VersionKey, { name: string; idea: string }> = {
  a: { name: "A · Guided setup", idea: "Step by step: subject, capabilities, review." },
  b: {
    name: "B · Live matrix",
    idea: "Capabilities and question types side by side, updating live.",
  },
  c: {
    name: "C · Settings table",
    idea: "A compact settings page, as it would sit in course Settings.",
  },
  d: {
    name: "D · Pick question types",
    idea: "Two steps: subject, then question types; graders are worked out for you.",
  },
};

export function CapabilitiesExperience() {
  const [version, setVersion] = useQueryState("v", parseAsStringLiteral(VERSIONS).withDefault("a"));

  return (
    <div className="min-h-screen bg-background">
      <header className="sticky top-0 z-20 border-b bg-background/95 backdrop-blur">
        <div className="mx-auto flex w-full max-w-6xl flex-wrap items-center gap-3 px-6 py-3">
          <div className="mr-auto">
            <div className="font-semibold text-sm">Course capabilities — prototype</div>
            <div className="text-muted-foreground text-xs">{VERSION_LABEL[version].idea}</div>
          </div>
          <div
            role="tablist"
            aria-label="Prototype version"
            className="flex rounded-lg border p-0.5"
          >
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
      <main className="mx-auto w-full max-w-6xl px-6 py-6">
        {version === "a" ? (
          <VersionA />
        ) : version === "b" ? (
          <VersionB />
        ) : version === "c" ? (
          <VersionC />
        ) : (
          <VersionD />
        )}
      </main>
    </div>
  );
}
