"use client";

/**
 * Generate one question from one chunk, then review it right here.
 *
 * The bulk sheet (`../generate-screen.tsx`) prices and runs a whole spec sheet
 * at once; this screen is its opposite — pick exactly one chunk, one type, one
 * difficulty, generate, and give feedback before ever touching another chunk.
 * It reuses the bulk sheet's chunk data (`useSheetRows`) and the Review
 * Queue's question/judges/feedback components verbatim — the only new pieces
 * are the outline tree, the PDF pane and the type/difficulty picker.
 */

import { parseAsInteger, parseAsStringLiteral, useQueryState } from "nuqs";
import { useEffect, useMemo, useState } from "react";
import { PageHeader } from "@/components/page-header";
import { EmptyState, QueryError, TableSkeleton } from "@/components/query-state";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { useApprovedCurriculum, useGenerateQuestions, useSection } from "@/lib/api/queries";
import { DIFFICULTIES, QUESTION_TYPES } from "../spec-sheet-types";
import { type SheetFilters, useSheetRows } from "../use-sheet-rows";
import { GenerateControls } from "./components/generate-controls";
import { OutlinePanel } from "./components/outline-panel";
import { PdfPageViewer } from "./components/pdf-page-viewer";
import { QuestionReview } from "./components/question-review";
import { QuestionsForChunk } from "./components/questions-for-chunk";

export function GenerateSingleScreen() {
  const [bookId, setBookId] = useQueryState("book", parseAsInteger);
  const [sectionId, setSectionId] = useQueryState("section", parseAsInteger);
  const [type, setType] = useQueryState(
    "type",
    parseAsStringLiteral(QUESTION_TYPES).withDefault("multiple_choice"),
  );
  const [difficulty, setDifficulty] = useQueryState(
    "difficulty",
    parseAsStringLiteral(DIFFICULTIES).withDefault("medium"),
  );
  const [search, setSearch] = useState("");
  const [produced, setProduced] = useState<SheetFilters["produced"]>("any");
  const [questionId, setQuestionId] = useState<number | null>(null);

  const filters: SheetFilters = useMemo(
    () => ({ bookId, chapterId: null, produced, search }),
    [bookId, produced, search],
  );
  const sheet = useSheetRows(filters);
  const approvedCurriculum = useApprovedCurriculum();
  const generate = useGenerateQuestions();

  // A single book to work in is the point of this screen — pick the only one
  // automatically rather than making that an extra click every time.
  useEffect(() => {
    if (bookId === null && sheet.books.length === 1) {
      void setBookId(sheet.books[0].id);
    }
  }, [bookId, sheet.books, setBookId]);

  const selectedRow = useMemo(
    () => sheet.allRows.find((row) => row.sectionId === sectionId) ?? null,
    [sheet.allRows, sectionId],
  );

  // A stale section id (wrong book, filtered out) points at nothing — drop it.
  useEffect(() => {
    if (!sheet.isPending && sectionId !== null && !selectedRow) {
      void setSectionId(null);
    }
  }, [sheet.isPending, sectionId, selectedRow, setSectionId]);

  const sectionDetail = useSection(bookId, sectionId, { enabled: selectedRow !== null });

  // The one path that changes which chunk is "current", whether it was a click
  // on the outline or the PDF pane scrolling a new chunk into view — either way
  // a question open from the previous chunk no longer applies.
  const selectSection = (id: number) => {
    setQuestionId(null);
    void setSectionId(id);
  };

  const runGenerate = () => {
    if (!selectedRow) return;
    setQuestionId(null);
    generate.mutate(
      {
        curriculum_version_id: approvedCurriculum.data?.version.id ?? null,
        question_type: type,
        difficulty,
        section_ids: [selectedRow.sectionId],
        all_sections_of_book: false,
      },
      {
        onSuccess: (response) => {
          const [id] = response.question_ids;
          if (id !== undefined) setQuestionId(id);
        },
      },
    );
  };

  return (
    <>
      <PageHeader
        title="Generate questions"
        summary="One chunk, one question at a time — pick a section, choose a type and difficulty, review, and give feedback right here."
        actions={
          <Select
            value={bookId === null ? "" : String(bookId)}
            onValueChange={(value) => {
              void setBookId(value ? Number(value) : null);
              void setSectionId(null);
              setQuestionId(null);
            }}
          >
            <SelectTrigger className="h-9 w-64" size="sm">
              <SelectValue placeholder="Choose a book" />
            </SelectTrigger>
            <SelectContent>
              {sheet.books.map((book) => (
                <SelectItem key={book.id} value={String(book.id)}>
                  {book.title}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
        }
      />

      {sheet.isError ? <QueryError error={sheet.error} /> : null}
      {sheet.isPending ? <TableSkeleton /> : null}

      {!sheet.isPending && bookId === null ? (
        <EmptyState title="Pick a book" hint="Choose a book above to see its chunks." />
      ) : null}

      {!sheet.isPending && bookId !== null ? (
        <div className="grid min-w-0 gap-4 xl:h-[calc(100dvh-9rem)] xl:grid-cols-[19rem_minmax(0,1fr)_22rem]">
          <div className="min-w-0 xl:min-h-0">
            <OutlinePanel
              chapters={sheet.chapters}
              rows={sheet.rows}
              selectedSectionId={sectionId}
              onSelect={selectSection}
              search={search}
              onSearchChange={setSearch}
              produced={produced}
              onProducedChange={setProduced}
            />
          </div>

          <div className="flex min-w-0 flex-col gap-4 xl:min-h-0">
            <div className="min-h-[560px] flex-1 xl:min-h-0">
              <PdfPageViewer
                bookId={bookId}
                rows={sheet.allRows}
                selectedSectionId={sectionId}
                onVisibleSectionChange={selectSection}
              />
            </div>
            {selectedRow && sectionDetail.data ? (
              <details className="shrink-0 rounded-[1rem] border p-3">
                <summary className="cursor-pointer font-mono text-[0.67rem] text-muted-foreground uppercase tracking-[0.16em]">
                  Source text — {selectedRow.title}
                </summary>
                <p className="mt-2 max-h-40 overflow-y-auto whitespace-pre-wrap text-sm leading-6">
                  {sectionDetail.data.text}
                </p>
              </details>
            ) : null}
            <div className="h-64 shrink-0">
              <QuestionsForChunk
                sectionId={sectionId}
                openQuestionId={questionId}
                onOpen={setQuestionId}
              />
            </div>
          </div>

          <div className="min-w-0 space-y-4 xl:min-h-0 xl:overflow-y-auto">
            {selectedRow ? (
              <GenerateControls
                type={type}
                onTypeChange={(value) => {
                  setQuestionId(null);
                  void setType(value);
                }}
                difficulty={difficulty}
                onDifficultyChange={(value) => {
                  setQuestionId(null);
                  void setDifficulty(value);
                }}
                onGenerate={runGenerate}
                isGenerating={generate.isPending}
              />
            ) : (
              <EmptyState
                title="Pick a chunk"
                hint="Scroll the PDF or select a section from the outline to generate from."
              />
            )}

            {generate.isError ? <QueryError error={generate.error} /> : null}

            {questionId !== null ? (
              <QuestionReview questionId={questionId} onGenerateAnother={runGenerate} />
            ) : null}
          </div>
        </div>
      ) : null}
    </>
  );
}
