import { SectionStub } from "@/components/section-stub";

export default function CurriculumPage() {
  return (
    <SectionStub
      sectionKey="curriculum"
      endpoints={[
        "GET  /api/curriculum/versions",
        "POST /api/curriculum/versions",
        "GET  /api/curriculum/versions/{version_id}",
        "GET  /api/curriculum/approved",
        "GET  /api/curriculum/subtopics/{subtopic_id}",
      ]}
    />
  );
}
