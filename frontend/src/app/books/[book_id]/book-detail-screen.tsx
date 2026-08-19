"use client";

/**
 * One book: what it declared, what it produced, and what it would cost to remove.
 *
 * A `partial` import is explained rather than badged and left: the document
 * validated, and something in it was incomplete or guessed at. The professor needs
 * to know that before generating questions from these sections.
 */

import { ArrowLeft, BookOpen, Pencil, Trash2 } from "lucide-react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { useState } from "react";
import { PageHeader } from "@/components/page-header";
import { QueryError, TableSkeleton } from "@/components/query-state";
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { useBook } from "@/lib/api/queries";
import { pluralise } from "@/lib/display";
import { authorLabel, BOOK_STATUS_LABEL, BOOK_STATUS_VARIANT, defects } from "../book-display";
import { BookDeleteDialog } from "../components/book-delete-dialog";
import { BookEditDialog } from "../components/book-edit-dialog";
import { BookProvenance } from "./components/book-provenance";
import { BookStructure } from "./components/book-structure";
import { WarningList } from "./components/warning-list";

export function BookDetailScreen({ bookId }: { bookId: number }) {
  const router = useRouter();
  const [editing, setEditing] = useState(false);
  const [deleting, setDeleting] = useState(false);
  const { data, isPending, isError, error } = useBook(bookId);

  if (isPending) {
    return (
      <>
        <PageHeader title="Book" />
        <TableSkeleton />
      </>
    );
  }

  if (isError) {
    return (
      <>
        <PageHeader title="Book" />
        <QueryError error={error} />
        <Link href="/books" className="text-muted-foreground text-sm hover:underline">
          ← All books
        </Link>
      </>
    );
  }

  const { book, chapters, warnings, section_count, grounded_question_count } = data;
  const declaredDefects = defects(warnings);

  return (
    <>
      <PageHeader
        title={book.title}
        summary={[
          authorLabel(book) === "—" ? null : authorLabel(book),
          pluralise(section_count, "section"),
          book.page_count ? `${book.page_count} pages` : null,
          grounded_question_count > 0
            ? `${pluralise(grounded_question_count, "question")} generated from it`
            : null,
        ]
          .filter(Boolean)
          .join(" · ")}
        actions={
          <>
            <Badge variant={BOOK_STATUS_VARIANT[book.status]}>
              {BOOK_STATUS_LABEL[book.status]}
            </Badge>
            <Button variant="outline" size="sm" onClick={() => setEditing(true)}>
              <Pencil />
              Edit
            </Button>
            <Button variant="outline" size="sm" onClick={() => setDeleting(true)}>
              <Trash2 />
              Delete
            </Button>
          </>
        }
      />

      <Link
        href="/books"
        className="flex w-fit items-center gap-1 text-muted-foreground text-sm hover:underline"
      >
        <ArrowLeft className="size-3" />
        All books
      </Link>

      {book.status === "partial" ? (
        <Alert>
          <BookOpen />
          <AlertTitle>Imported with caveats</AlertTitle>
          <AlertDescription>
            The document validated, but it declares caveats: something was incomplete, or its
            producer guessed at a boundary. Read the warnings below before generating questions from
            these sections.
          </AlertDescription>
        </Alert>
      ) : null}

      {warnings.length > 0 ? (
        <Card>
          <CardHeader>
            <CardTitle>Declared warnings</CardTitle>
            <CardDescription>
              {declaredDefects.length > 0
                ? `${pluralise(declaredDefects.length, "defect")} of ${pluralise(warnings.length, "warning")}. Only a defect makes a book partial.`
                : "Stated as facts about the source, not faults in the document."}
            </CardDescription>
          </CardHeader>
          <CardContent>
            <WarningList warnings={warnings} />
          </CardContent>
        </Card>
      ) : null}

      {book.notes ? (
        <Card>
          <CardHeader>
            <CardTitle>Notes</CardTitle>
          </CardHeader>
          <CardContent>
            <p className="whitespace-pre-wrap text-sm">{book.notes}</p>
          </CardContent>
        </Card>
      ) : null}

      <Card>
        <CardHeader>
          <CardTitle>Structure</CardTitle>
          <CardDescription>
            Declared by the document. {pluralise(chapters.length, "chapter")},{" "}
            {pluralise(section_count, "section")} — the section is the unit questions are generated
            from.
          </CardDescription>
        </CardHeader>
        <CardContent>
          <BookStructure bookId={book.id} chapters={chapters} />
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle>Provenance</CardTitle>
        </CardHeader>
        <CardContent>
          <BookProvenance book={book} />
        </CardContent>
      </Card>

      <BookEditDialog
        key={`edit-${book.id}`}
        book={book}
        open={editing}
        onOpenChange={setEditing}
      />
      <BookDeleteDialog
        key={`delete-${book.id}`}
        book={book}
        open={deleting}
        onOpenChange={setDeleting}
        onDeleted={() => router.push("/books")}
      />
    </>
  );
}
