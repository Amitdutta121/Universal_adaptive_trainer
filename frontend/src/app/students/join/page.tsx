import { Suspense } from "react";
import { JoinClassroomScreen } from "./join-classroom-screen";

export default function JoinClassroomPage() {
  return (
    <Suspense fallback={null}>
      <JoinClassroomScreen />
    </Suspense>
  );
}
