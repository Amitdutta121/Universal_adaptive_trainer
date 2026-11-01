/**
 * The single-chunk generation route shell.
 *
 * `GenerateSingleScreen` keeps its book/section/type/difficulty in the URL
 * (`nuqs`), which Next requires to sit inside a Suspense boundary — see
 * `../page.tsx` for the same reasoning on the bulk sheet.
 */

import { Suspense } from "react";
import { PageHeader } from "@/components/page-header";
import { TableSkeleton } from "@/components/query-state";
import { GenerateSingleScreen } from "./generate-single-screen";

export default function GenerateSingleQuestionPage() {
  return (
    <Suspense
      fallback={
        <>
          <PageHeader
            title="Generate questions"
            summary="One chunk, one question at a time — pick a section, generate, and review it here."
          />
          <TableSkeleton />
        </>
      }
    >
      <GenerateSingleScreen />
    </Suspense>
  );
}
