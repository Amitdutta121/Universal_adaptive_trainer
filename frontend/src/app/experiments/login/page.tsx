/**
 * `/experiments/login` — design prototypes of the sign-in page, four versions behind one switcher,
 * on mock data only (no API). `AppChrome` skips this path. The real page is `app/login`.
 */

import type { Metadata } from "next";
import { Suspense } from "react";
import { LoginExperience } from "./experience";

export const metadata: Metadata = {
  title: "Login — design prototype",
  description: "Four mock-data versions of the sign-in page, for design review.",
};

export default function LoginExperimentPage() {
  return (
    <Suspense>
      <LoginExperience />
    </Suspense>
  );
}
