import { SectionStub } from "@/components/section-stub";

export default function StudentsPage() {
  return (
    <SectionStub
      sectionKey="students"
      endpoints={[
        "GET  /api/students",
        "POST /api/students",
        "GET  /api/students/{student_id}/progress",
        "POST /api/training-sessions",
        "GET  /api/training-sessions/{id}/next",
        "POST /api/attempts/{attempt_id}/answer",
      ]}
    />
  );
}
