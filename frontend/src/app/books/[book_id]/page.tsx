/**
 * One book's route shell.
 *
 * `params` is async in Next 16; the id is resolved here and the screen below is a
 * client component because this page edits and deletes the book it is showing.
 */

import { notFound } from "next/navigation";
import { BookDetailScreen } from "./book-detail-screen";

export default async function BookDetailPage(props: PageProps<"/books/[book_id]">) {
  const { book_id } = await props.params;
  const id = Number(book_id);
  if (!Number.isInteger(id)) notFound();
  return <BookDetailScreen bookId={id} />;
}
