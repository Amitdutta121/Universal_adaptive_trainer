import { SectionStub } from "@/components/section-stub";

export default function InstructionsPage() {
  return (
    <SectionStub
      sectionKey="instructions"
      endpoints={["GET  /api/instructions", "POST /api/instructions/{question_type}/refresh"]}
    />
  );
}
