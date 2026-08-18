import { SectionStub } from "@/components/section-stub";

export default function FeedbackPage() {
  return (
    <SectionStub
      sectionKey="feedback"
      endpoints={[
        "GET /api/reviews",
        "GET /api/reviews/stats",
        "GET /api/calibration/quadrant",
        "GET /api/calibration/results",
        "GET /api/calibration/pairs",
        "GET /api/calibration/trend",
      ]}
    />
  );
}
