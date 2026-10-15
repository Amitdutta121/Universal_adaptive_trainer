/**
 * The tutorials route: generate and preview tutorial blocks per subtopic
 * (`/api/tutorial-recipes`, `/api/tutorial-blocks`, Phase 5).
 */

import { PageHeader } from "@/components/page-header";
import { SECTIONS_BY_KEY } from "@/lib/navigation";
import { TutorialsScreen } from "./tutorials-screen";

export default function TutorialsPage() {
  const section = SECTIONS_BY_KEY.tutorials;
  return (
    <div className="space-y-6 pb-16">
      <PageHeader title={section.label} summary={section.summary} />
      <TutorialsScreen />
    </div>
  );
}
