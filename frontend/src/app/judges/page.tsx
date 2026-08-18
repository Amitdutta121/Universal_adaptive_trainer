import { SectionStub } from "@/components/section-stub";

export default function JudgesPage() {
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
