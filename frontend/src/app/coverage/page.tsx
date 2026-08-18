import { SectionStub } from "@/components/section-stub";

export default function CoveragePage() {
  return (
    <SectionStub
      sectionKey="coverage"
      endpoints={[
        "GET  /api/coverage",
        "POST /api/coverage/generation-runs",
        "GET  /api/question-sets",
        "POST /api/question-sets",
      ]}
    />
  );
}
