/**
 * The dashboard.
 *
 * A server component: it fetches through the same typed client the browser uses,
 * but on the Next.js server, so the first paint carries real counts and no loading
 * skeleton. Interactive screens (filters, mutations, polling) use TanStack Query on
 * the client instead — see `app/questions/page.tsx`.
 */

import Link from "next/link";
import { PageHeader } from "@/components/page-header";
import { QueryError } from "@/components/query-state";
import { Badge } from "@/components/ui/badge";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { api, unwrap } from "@/lib/api/client";
import type { Counts, Health } from "@/lib/api/types";
import { NAV_SECTIONS } from "@/lib/navigation";

// Counts change whenever a question is generated or reviewed; never cache them.
export const dynamic = "force-dynamic";

/** Which dashboard card each count belongs to. Sections with no count show none. */
const COUNT_KEYS: Partial<Record<string, keyof Counts>> = {
  books: "books",
  curriculum: "curriculum_versions",
  questions: "questions",
  review: "reviews",
  instructions: "learned_instructions",
  students: "students",
};

export default async function DashboardPage() {
  let counts: Counts | null = null;
  let health: Health | null = null;
  let error: unknown = null;

  try {
    [counts, health] = await Promise.all([
      unwrap(api.GET("/api/counts")),
      unwrap(api.GET("/api/health")),
    ]);
  } catch (caught) {
    error = caught;
  }

  return (
    <>
      <PageHeader
        title="Professor console"
        summary="Content generation and adaptive training, over one shared question bank."
        actions={
          health ? (
            <>
              <Badge variant={health.database_ok ? "secondary" : "destructive"}>
                {health.database_ok ? "database ok" : "database unreachable"}
              </Badge>
              <Badge variant="outline" title={health.llm_status}>
                {health.environment} · v{health.version}
              </Badge>
            </>
          ) : null
        }
      />

      {error ? <QueryError error={error} /> : null}

      <div className="dashboard-grid">
        {NAV_SECTIONS.map((section) => {
          const countKey = COUNT_KEYS[section.key];
          const count = counts && countKey ? counts[countKey] : null;
          const Icon = section.icon;
          return (
            <Link key={section.key} href={section.path} className="group">
              <Card className="dashboard-card h-full border">
                <CardHeader className="gap-3">
                  <div className="review-eyebrow">{section.key.replace(/_/g, " ")}</div>
                  <div className="flex items-start justify-between gap-2">
                    <div className="flex items-center gap-2">
                      <Icon className="size-4 text-muted-foreground" />
                      <CardTitle className="text-base">{section.label}</CardTitle>
                    </div>
                    {count === null ? null : (
                      <span className="font-semibold text-2xl tabular-nums tracking-[-0.03em]">
                        {count}
                      </span>
                    )}
                  </div>
                  <CardDescription className="leading-6">{section.summary}</CardDescription>
                </CardHeader>
                <CardContent className="pt-0" />
              </Card>
            </Link>
          );
        })}
      </div>
    </>
  );
}
