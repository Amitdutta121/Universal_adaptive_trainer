import { Suspense } from "react";
import { RosterScreen } from "./roster-screen";

export default function StudentsRosterPage() {
  return (
    <Suspense fallback={null}>
      <RosterScreen />
    </Suspense>
  );
}
