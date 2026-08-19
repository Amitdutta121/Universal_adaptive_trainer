/**
 * The books route shell.
 *
 * `BooksScreen` keeps its search and status filter in the URL, which means it
 * reads search params, which Next requires to sit inside a Suspense boundary —
 * without one the whole route opts out of static rendering at build time.
 */

import { Suspense } from "react";
import { PageHeader } from "@/components/page-header";
import { TableSkeleton } from "@/components/query-state";
import { SECTIONS_BY_KEY } from "@/lib/navigation";
import { BooksScreen } from "./books-screen";

export default function BooksPage() {
  const section = SECTIONS_BY_KEY.books;
  return (
    <Suspense
      fallback={
        <>
          <PageHeader title={section.label} summary={section.summary} />
          <TableSkeleton />
        </>
      }
    >
      <BooksScreen />
    </Suspense>
  );
}
