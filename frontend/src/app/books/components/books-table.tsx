"use client";

/**
 * The imported books, newest first.
 *
 * Status carries a tooltip rather than an explanation in a column: `partial` is
 * the one value a professor has to interpret, and it means "validated, with
 * caveats declared" — not "failed".
 */

import { MoreHorizontal, Pencil, Trash2 } from "lucide-react";
import Link from "next/link";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import { Tooltip, TooltipContent, TooltipTrigger } from "@/components/ui/tooltip";
import type { BookSummary } from "@/lib/api/types";
import { formatTimestamp } from "@/lib/display";
import {
  authorLabel,
  BOOK_STATUS_LABEL,
  BOOK_STATUS_MEANING,
  BOOK_STATUS_VARIANT,
} from "../book-display";

export function BooksTable({
  books,
  onEdit,
  onDelete,
}: {
  books: readonly BookSummary[];
  onEdit: (book: BookSummary) => void;
  onDelete: (book: BookSummary) => void;
}) {
  return (
    <Table>
      <TableHeader>
        <TableRow>
          <TableHead>Title</TableHead>
          <TableHead>Author</TableHead>
          <TableHead>Status</TableHead>
          <TableHead className="text-right">Pages</TableHead>
          <TableHead>Warnings</TableHead>
          <TableHead>Producer</TableHead>
          <TableHead>Imported</TableHead>
          <TableHead className="w-10" />
        </TableRow>
      </TableHeader>
      <TableBody>
        {books.map((book) => (
          <TableRow key={book.id}>
            <TableCell className="font-medium">
              <Link href={`/books/${book.id}`} className="hover:underline">
                {book.title}
              </Link>
              {book.notes ? (
                <p className="mt-0.5 line-clamp-1 text-muted-foreground text-xs">{book.notes}</p>
              ) : null}
            </TableCell>
            <TableCell className="text-muted-foreground">{authorLabel(book)}</TableCell>
            <TableCell>
              <Tooltip>
                <TooltipTrigger asChild>
                  <Badge variant={BOOK_STATUS_VARIANT[book.status]}>
                    {BOOK_STATUS_LABEL[book.status]}
                  </Badge>
                </TooltipTrigger>
                <TooltipContent>{BOOK_STATUS_MEANING[book.status]}</TooltipContent>
              </Tooltip>
            </TableCell>
            <TableCell className="text-right tabular-nums">{book.page_count ?? "—"}</TableCell>
            <TableCell className="text-muted-foreground text-sm">
              {book.warning_count === 0 ? (
                "—"
              ) : (
                <>
                  {book.warning_count}
                  {book.defect_count > 0 ? (
                    <span className="text-destructive"> · {book.defect_count} defect</span>
                  ) : null}
                </>
              )}
            </TableCell>
            <TableCell className="font-mono text-muted-foreground text-xs">
              {book.producer ?? "—"}
            </TableCell>
            <TableCell className="text-muted-foreground text-sm">
              {formatTimestamp(book.imported_at ?? book.created_at)}
            </TableCell>
            <TableCell>
              <DropdownMenu>
                <DropdownMenuTrigger asChild>
                  <Button variant="ghost" size="icon" aria-label={`Actions for ${book.title}`}>
                    <MoreHorizontal />
                  </Button>
                </DropdownMenuTrigger>
                <DropdownMenuContent align="end">
                  <DropdownMenuItem onSelect={() => onEdit(book)}>
                    <Pencil />
                    Edit labels
                  </DropdownMenuItem>
                  <DropdownMenuItem variant="destructive" onSelect={() => onDelete(book)}>
                    <Trash2 />
                    Delete
                  </DropdownMenuItem>
                </DropdownMenuContent>
              </DropdownMenu>
            </TableCell>
          </TableRow>
        ))}
      </TableBody>
    </Table>
  );
}
