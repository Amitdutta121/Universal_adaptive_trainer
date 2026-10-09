/**
 * The judges route: the difficulty judge, the topic-alignment judge, the generator
 * guidelines (`/api/guidelines`, ADR-063), and this
 * taxonomy's custom rules.
 *
 * The two built-in judges are backed by `GET/PUT/DELETE /api/judge-prompts`
 * (ADR-038). Editing a prompt re-names the panel, so the screen shows the
 * rubric version it answers under. Custom rules are `GET/POST/PATCH
 * /api/custom-judges` for the approved taxonomy.
 */

import { PageHeader } from "@/components/page-header";
import { JudgesScreen } from "./judges-screen";
import { RunJudgesButton } from "./run-judges-button";

export default function JudgesPage() {
  return (
    <div className="space-y-6 pb-16">
      <PageHeader
        title="Judges"
        summary="The difficulty judge, the topic-alignment judge, the generator guidelines learned from your reviews, and this taxonomy's custom rules. Edit a prompt to change what a built-in judge checks, or revert it to the text it shipped with."
        actions={<RunJudgesButton />}
      />
      <JudgesScreen />
    </div>
  );
}
