"use client";

/**
 * Live first-run checklist for the landing page.
 *
 * Every row is read from `GET /api/health` -- the same payload the sidebar uses --
 * so a new install can see, before signing in, which of its components are
 * actually up. `describeHealth` is split out so the mapping from payload to row
 * is testable without rendering.
 */

import { useHealth } from "@/lib/api/queries";
import type { Health } from "@/lib/api/types";

export type StatusTone = "ok" | "warn" | "critical" | "idle";

export interface StatusRow {
  key: string;
  label: string;
  tone: StatusTone;
  detail: string;
}

const WAITING = "Waiting for the API";

/** Maps the health query state onto the four checklist rows. */
export function describeHealth(
  health: Health | undefined,
  state: "pending" | "error" | "success",
): StatusRow[] {
  if (state === "pending") {
    return [
      { key: "api", label: "Backend API", tone: "idle", detail: "Checking…" },
      { key: "db", label: "Database", tone: "idle", detail: WAITING },
      { key: "llm", label: "LLM provider", tone: "idle", detail: WAITING },
      { key: "account", label: "Dev account", tone: "idle", detail: WAITING },
    ];
  }
  if (state === "error" || !health) {
    return [
      {
        key: "api",
        label: "Backend API",
        tone: "critical",
        detail: "Not reachable. See \"Start it\" below",
      },
      { key: "db", label: "Database", tone: "idle", detail: WAITING },
      { key: "llm", label: "LLM provider", tone: "idle", detail: WAITING },
      { key: "account", label: "Dev account", tone: "idle", detail: WAITING },
    ];
  }
  const isDevelopment = health.environment === "development";
  return [
    { key: "api", label: "Backend API", tone: "ok", detail: `Reachable · v${health.version}` },
    {
      key: "db",
      label: "Database",
      tone: health.database_ok ? "ok" : "critical",
      detail: health.database_ok ? "Connected" : "Unreachable. Check DATABASE_URL",
    },
    {
      key: "llm",
      label: "LLM provider",
      tone: health.llm_configured ? "ok" : "warn",
      detail: health.llm_configured
        ? "Configured"
        : "Not configured. Optional, only generation and the judges need it",
    },
    {
      key: "account",
      label: "Dev account",
      tone: isDevelopment ? "ok" : "warn",
      detail: isDevelopment
        ? "Seeded (ENVIRONMENT=development)"
        : `Not seeded (ENVIRONMENT=${health.environment})`,
    },
  ];
}

const DOT_TONE: Record<StatusTone, string> = {
  ok: "bg-[var(--ok-solid)]",
  warn: "bg-[var(--warn-solid)]",
  critical: "bg-[var(--critical-solid)]",
  idle: "bg-[var(--hairline-2)]",
};

export function SetupStatus() {
  const { data, status } = useHealth();
  const rows = describeHealth(data, status);

  return (
    <ul className="divide-y divide-border" aria-live="polite">
      {rows.map((row) => (
        <li key={row.key} className="flex items-start gap-3 py-3 first:pt-0 last:pb-0">
          <span
            aria-hidden="true"
            className={`mt-1.5 size-2 shrink-0 rounded-full ${DOT_TONE[row.tone]}`}
          />
          <div className="min-w-0">
            <div className="font-medium text-sm">{row.label}</div>
            <div className="text-muted-foreground text-sm">{row.detail}</div>
          </div>
        </li>
      ))}
    </ul>
  );
}
