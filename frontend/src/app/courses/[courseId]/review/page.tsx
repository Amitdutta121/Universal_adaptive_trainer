import { Suspense } from "react";
import { ReviewScreen } from "./review-screen";

export default function ReviewPage() {
  return (
    <Suspense fallback={null}>
      <ReviewScreen />
    </Suspense>
  );
}
