/**
 * The judges route: the four advisory reviewers, and the prompt each one runs.
 *
 * Backed by `GET/PUT/DELETE /api/judge-prompts` and `POST /api/judge-prompts/
 * {metric}/refresh` (ADR-038, ADR-039). Editing or re-learning a prompt
 * re-names the panel, so the screen shows the rubric version it answers under.
 */

import { PageHeader } from "@/components/page-header";
import { JudgesScreen } from "./judges-screen";

export default function JudgesPage() {
  return (
    <div className="space-y-6 pb-16">
      <PageHeader
        title="Judges"
        summary="The four advisory reviewers, and the prompt each one follows. Edit a prompt to repair a judge, or re-learn it from the questions it got wrong."
      />
      <JudgesScreen />
    </div>
  );
}
