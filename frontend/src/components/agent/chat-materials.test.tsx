import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { ChatMaterialsButton, MaterialsPanel } from "./chat-materials";

const importBook = vi.fn();
const deleteBook = vi.fn();
let books: { id: number; title: string; original_filename: string }[] = [];

vi.mock("@/lib/api/queries", () => ({
  useBooks: () => ({ isLoading: false, data: { books, total: books.length } }),
  useConfig: () => ({ data: { supported_book_extensions: [".pdf"], max_book_upload_mb: 50 } }),
  useImportBook: () => ({ mutateAsync: importBook, isPending: false }),
  useDeleteBook: () => ({ mutateAsync: deleteBook, isPending: false }),
}));
vi.mock("@/app/courses/[courseId]/books/components/book-import-dialog", () => ({
  uploadProblem: (file: File) => (file.name.endsWith(".pdf") ? null : "Only .pdf files."),
}));
vi.mock("sonner", () => ({ toast: { info: vi.fn(), error: vi.fn(), success: vi.fn() } }));

beforeEach(() => {
  importBook.mockReset().mockResolvedValue({ job_id: "j1" });
  deleteBook.mockReset().mockResolvedValue({});
  books = [
    { id: 26, title: "AI in Games syllabus", original_filename: "syllabus.pdf" },
    { id: 27, title: "Lecture 1 slides", original_filename: "lecture1.pdf" },
  ];
});

describe("ChatMaterialsButton", () => {
  it("shows how many files the course has", () => {
    render(<ChatMaterialsButton open={false} onToggle={() => {}} />);
    expect(screen.getByRole("button", { name: "Course files (2)" })).toBeTruthy();
  });
});

describe("MaterialsPanel", () => {
  it("lists the course's files", () => {
    render(<MaterialsPanel onClose={() => {}} />);
    expect(screen.getByText("AI in Games syllabus")).toBeTruthy();
    expect(screen.getByText("Lecture 1 slides")).toBeTruthy();
  });

  it("removes a file only after a second, in-place confirmation", async () => {
    render(<MaterialsPanel onClose={() => {}} />);
    fireEvent.click(screen.getByRole("button", { name: "Remove Lecture 1 slides" }));
    expect(deleteBook).not.toHaveBeenCalled();
    fireEvent.click(screen.getByRole("button", { name: "Remove" }));
    await waitFor(() => expect(deleteBook).toHaveBeenCalledWith({ bookId: 27 }));
  });

  it("imports added files it accepts and skips the rest", async () => {
    render(<MaterialsPanel onClose={() => {}} />);
    const pdf = new File(["x"], "notes.pdf", { type: "application/pdf" });
    const zip = new File(["x"], "archive.zip", { type: "application/zip" });
    fireEvent.change(screen.getByLabelText("Add files"), { target: { files: [pdf, zip] } });
    await waitFor(() => expect(importBook).toHaveBeenCalledTimes(1));
    expect(importBook).toHaveBeenCalledWith({ file: pdf });
  });

  it("says what to add when there are no files", () => {
    books = [];
    render(<MaterialsPanel onClose={() => {}} />);
    expect(screen.getByText(/No files yet/)).toBeTruthy();
  });
});
