/**
 * The judges route shell.
 *
 * The shipped judges feature is per-metric judge-prompt editing (see the
 * endpoints below). In development this instead previews a reframed concept
 * — an eval gallery scored against a shared gold set, with a way to draft
 * and measure your own eval — on mock data, since no gold-set/alignment API
 * exists yet. See `judges-screen.tsx` and `mock-data.ts`.
 */

import { PageHeader } from "@/components/page-header";
import { SectionStub } from "@/components/section-stub";
import { JudgesScreen } from "./judges-screen";

export default function JudgesPage() {
  if (process.env.NODE_ENV === "production") {
    return (
      <SectionStub
        sectionKey="judges"
        endpoints={[
          "GET    /api/judge-prompts",
          "PUT    /api/judge-prompts/{metric}",
          "DELETE /api/judge-prompts/{metric}",
          "POST   /api/judge-prompts/{metric}/refresh",
          "POST   /api/evaluation/batch-runs",
          "POST   /api/evaluation/batch-runs/{run_id}/poll",
        ]}
      />
    );
  }
  return (
    <div className="space-y-6 pb-16">
      <PageHeader
        title="Evals"
        summary="Existing evals, scored against a human-graded gold set — plus a way to draft your own and measure how well it aligns."
      />
      <JudgesScreen />
    </div>
  );
}
