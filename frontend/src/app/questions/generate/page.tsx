/**
 * The generate-from-chunks route shell.
 *
 * `GenerateScreen` keeps its filters in the URL, which means it reads search
 * params, which Next requires to sit inside a Suspense boundary — without one the
 * whole route opts out of static rendering at build time. The boundary lives here
 * so the screen stays about generation.
 */

import { Suspense } from "react";
import { PageHeader } from "@/components/page-header";
import { TableSkeleton } from "@/components/query-state";
import { GenerateScreen } from "./generate-screen";

export default function GenerateQuestionsPage() {
  return (
    <Suspense
      fallback={
        <>
          <PageHeader
            title="Generate from chunks"
            summary="Set what each textbook chunk should produce, across every book, then run it once."
          />
          <TableSkeleton />
        </>
      }
    >
      <GenerateScreen />
    </Suspense>
  );
}
