/**
 * A section whose screen has not been ported from the Jinja UI yet.
 *
 * It names the API routes that are already generated and typed, so the next person
 * knows exactly where to start, and it never renders invented data.
 */

import { PageHeader } from "@/components/page-header";
import { NotBuiltYet } from "@/components/query-state";
import { SECTIONS_BY_KEY } from "@/lib/navigation";

export function SectionStub({
  sectionKey,
  endpoints,
}: {
  sectionKey: keyof typeof SECTIONS_BY_KEY;
  endpoints: readonly string[];
}) {
  const section = SECTIONS_BY_KEY[sectionKey];
  return (
    <>
      <PageHeader title={section.label} summary={section.summary} />
      <NotBuiltYet endpoints={endpoints} />
    </>
  );
}
