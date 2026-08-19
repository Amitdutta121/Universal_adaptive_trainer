"use client";

/**
 * Import a book document, from a saved file or from pasted text.
 *
 * Inline on the page rather than behind a dialog: importing is what this screen
 * is for, and a professor arriving with a document in the clipboard should not
 * have to open anything first.
 *
 * Both paths end in the same multipart upload, because both are the same
 * document: a reply from an assistant is text long before it is a file.
 *
 * A rejection is shown with the backend's own message and detail — "the document
 * does not match the expected structure", and the field that was wrong — because
 * that text is what tells them what to fix. Nothing is stored on a rejection, so
 * what they typed is left exactly where it is.
 */

import { Upload } from "lucide-react";
import { useId, useState } from "react";
import { toast } from "sonner";
import { QueryError } from "@/components/query-state";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { Textarea } from "@/components/ui/textarea";
import { useImportBook } from "@/lib/api/queries";
import type { BookDocumentGuide } from "@/lib/api/types";
import { exceedsUploadLimit, fileFromPastedJson, jsonProblem } from "@/lib/json-document";
import { PASTED_BOOK_FILENAME, titleOverride } from "../book-document";

type Source = "file" | "paste";

export function BookUploadCard({ guide }: { guide: BookDocumentGuide | undefined }) {
  const [source, setSource] = useState<Source>("file");
  const [file, setFile] = useState<File | null>(null);
  const [pasted, setPasted] = useState("");
  const [title, setTitle] = useState("");
  const [localProblem, setLocalProblem] = useState<string | null>(null);
  const importBook = useImportBook();

  const fileFieldId = useId();
  const pasteFieldId = useId();
  const titleFieldId = useId();

  const accept = guide?.supported_extensions.join(",") ?? ".json";
  const maxUploadMb = guide?.max_upload_mb;

  /** The document to send, or `null` with `localProblem` explaining why not. */
  function documentToSend(): File | null {
    if (source === "file") {
      if (!file) {
        setLocalProblem("Choose a .json file, or switch to Paste JSON.");
        return null;
      }
      if (maxUploadMb !== undefined && exceedsUploadLimit(file.size, maxUploadMb)) {
        setLocalProblem(`This file is larger than the ${maxUploadMb} MB limit.`);
        return null;
      }
      return file;
    }

    const problem = jsonProblem(pasted, "book document");
    if (problem) {
      setLocalProblem(problem);
      return null;
    }
    return fileFromPastedJson(pasted, PASTED_BOOK_FILENAME);
  }

  async function submit(event: React.FormEvent) {
    event.preventDefault();
    setLocalProblem(null);
    importBook.reset();

    const document = documentToSend();
    if (!document) return;

    try {
      const book = await importBook.mutateAsync({ file: document, title: titleOverride(title) });
      toast.success(`Imported “${book.title}”`, {
        description:
          book.status === "partial"
            ? "The document validated but declares caveats — it is marked partial."
            : "The document validated with no caveats declared.",
      });
      // Only cleared on success: a refused document is still the professor's work.
      setFile(null);
      setPasted("");
      setTitle("");
      (event.target as HTMLFormElement).reset();
    } catch {
      // Rendered from `importBook.error` below, with the backend's own wording.
    }
  }

  return (
    <Card>
      <CardHeader>
        <CardTitle className="flex items-center gap-2">
          <Upload className="size-4 text-muted-foreground" />
          Import a book document
        </CardTitle>
        <CardDescription>
          Structured book JSON only{maxUploadMb ? `, up to ${maxUploadMb} MB` : ""}. An invalid
          document is refused in full — nothing is stored, and you can correct it and try again.
        </CardDescription>
      </CardHeader>

      <CardContent>
        <form onSubmit={submit} className="space-y-4">
          <Tabs value={source} onValueChange={(value) => setSource(value as Source)}>
            <TabsList>
              <TabsTrigger value="file">Upload file</TabsTrigger>
              <TabsTrigger value="paste">Paste JSON</TabsTrigger>
            </TabsList>

            <TabsContent value="file" className="mt-3 space-y-2">
              <Label htmlFor={fileFieldId}>Book JSON document</Label>
              <Input
                id={fileFieldId}
                type="file"
                accept={accept}
                className="max-w-md"
                onChange={(event) => {
                  setFile(event.target.files?.[0] ?? null);
                  setLocalProblem(null);
                }}
              />
              <p className="text-muted-foreground text-xs">
                Accepted: {accept}
                {guide ? ` (schema version ${guide.schema_version})` : ""}. A PDF or EPUB cannot be
                imported — convert it to a document first.
              </p>
            </TabsContent>

            <TabsContent value="paste" className="mt-3 space-y-2">
              <Label htmlFor={pasteFieldId}>Book JSON document</Label>
              <Textarea
                id={pasteFieldId}
                value={pasted}
                onChange={(event) => {
                  setPasted(event.target.value);
                  setLocalProblem(null);
                }}
                placeholder='{"schema_version": "1", "title": "…", "chapters": [ … ]}'
                className="h-[12rem] font-mono text-xs"
                spellCheck={false}
              />
              <p className="text-muted-foreground text-xs">
                Paste the assistant's reply. Include the JSON only — no surrounding code fence.
              </p>
            </TabsContent>
          </Tabs>

          <div className="flex flex-wrap items-end gap-3">
            <div className="min-w-0 flex-1 space-y-2">
              <Label htmlFor={titleFieldId}>
                Title <span className="text-muted-foreground">(optional)</span>
              </Label>
              <Input
                id={titleFieldId}
                value={title}
                maxLength={500}
                className="max-w-md"
                onChange={(event) => setTitle(event.target.value)}
                placeholder="Leave blank to use the title inside the document"
              />
            </div>
            <Button type="submit" disabled={importBook.isPending}>
              {importBook.isPending ? "Validating…" : "Import book"}
            </Button>
          </div>

          {localProblem ? (
            <p className="rounded-md border border-destructive/40 bg-destructive/5 p-3 text-destructive text-sm">
              {localProblem}
            </p>
          ) : null}
          {importBook.error ? <QueryError error={importBook.error} /> : null}
        </form>
      </CardContent>
    </Card>
  );
}
