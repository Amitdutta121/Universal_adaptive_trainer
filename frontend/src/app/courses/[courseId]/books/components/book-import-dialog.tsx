"use client";

/**
 * Import a book document: a modal opened from the books page header.
 *
 * The common case is one file — a PDF or a book JSON document — so that is all
 * the modal shows by default. Everything else sits under "Advanced options":
 * pasting an assistant's JSON reply instead of a file, overriding the title, and
 * the prompt / example / allowed values for a professor who has no document yet.
 *
 * Both paths end in the same multipart upload, because both are the same
 * document: a reply from an assistant is text long before it is a file.
 *
 * Submitting runs only the quick checks (type, size, a JSON document's structure,
 * whether a PDF opens) and starts the import as a background job: the modal closes
 * and the job's run window opens (`?job=`), so a long PDF never holds the professor
 * here. The Jobs panel announces when the book is ready, or why it was refused.
 *
 * A quick-check rejection is shown with the backend's own message and detail — "the
 * document does not match the expected structure", and the field that was wrong —
 * because that text is what tells them what to fix. Nothing is stored on a rejection,
 * so what they entered is left where it is and the modal stays open. The form lives
 * inside the dialog's content, so closing the modal clears it.
 */

import { ChevronDown, Upload } from "lucide-react";
import { parseAsString, useQueryState } from "nuqs";
import { useId, useState } from "react";
import { QueryError } from "@/components/query-state";
import { Button } from "@/components/ui/button";
import { Collapsible, CollapsibleContent, CollapsibleTrigger } from "@/components/ui/collapsible";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import { useBookDocumentGuide, useImportBook } from "@/lib/api/queries";
import { exceedsUploadLimit, fileFromPastedJson, jsonProblem } from "@/lib/json-document";
import { PASTED_BOOK_FILENAME, titleOverride } from "../book-document";
import { DocumentGuideCard } from "./document-guide-card";

function ImportForm({ onImported }: { onImported: () => void }) {
  const guide = useBookDocumentGuide();
  const [file, setFile] = useState<File | null>(null);
  const [pasted, setPasted] = useState("");
  const [title, setTitle] = useState("");
  const [localProblem, setLocalProblem] = useState<string | null>(null);
  const importBook = useImportBook();
  const [, setJobParam] = useQueryState("job", parseAsString);

  const fileFieldId = useId();
  const pasteFieldId = useId();
  const titleFieldId = useId();

  const accept = guide.data?.supported_extensions.join(",") ?? ".json";
  const maxUploadMb = guide.data?.max_upload_mb;

  /** The document to send, or `null` with `localProblem` explaining why not. */
  function documentToSend(): File | null {
    const hasPasted = pasted.trim() !== "";
    if (file && hasPasted) {
      setLocalProblem("Choose a file or paste JSON, not both.");
      return null;
    }
    if (hasPasted) {
      const problem = jsonProblem(pasted, "book document");
      if (problem) {
        setLocalProblem(problem);
        return null;
      }
      return fileFromPastedJson(pasted, PASTED_BOOK_FILENAME);
    }
    if (!file) {
      setLocalProblem("Choose a file, or paste JSON under Advanced options.");
      return null;
    }
    if (maxUploadMb !== undefined && exceedsUploadLimit(file.size, maxUploadMb)) {
      setLocalProblem(`This file is larger than the ${maxUploadMb} MB limit.`);
      return null;
    }
    return file;
  }

  async function submit(event: React.FormEvent) {
    event.preventDefault();
    setLocalProblem(null);
    importBook.reset();

    const document = documentToSend();
    if (!document) return;

    try {
      const started = await importBook.mutateAsync({
        file: document,
        title: titleOverride(title),
      });
      // Only closed once accepted: a refused document is still the professor's work.
      onImported();
      void setJobParam(started.job_id);
    } catch {
      // Rendered from `importBook.error` below, with the backend's own wording.
    }
  }

  return (
    <form onSubmit={(event) => void submit(event)} className="min-w-0 space-y-4">
      <div className="space-y-2">
        <Label htmlFor={fileFieldId}>Book file</Label>
        <Input
          id={fileFieldId}
          type="file"
          accept={accept}
          onChange={(event) => {
            setFile(event.target.files?.[0] ?? null);
            setLocalProblem(null);
          }}
        />
        <p className="text-muted-foreground text-xs">
          {accept.split(",").join(", ")}
          {maxUploadMb ? `, up to ${maxUploadMb} MB` : ""}.
        </p>
      </div>

      <Collapsible className="group/advanced rounded-lg border">
        <CollapsibleTrigger asChild>
          <Button type="button" variant="ghost" size="sm" className="w-full justify-between">
            Advanced options
            <ChevronDown className="transition-transform group-data-[state=open]/advanced:rotate-180" />
          </Button>
        </CollapsibleTrigger>
        <CollapsibleContent className="min-w-0 space-y-4 border-t p-3">
          <div className="space-y-2">
            <Label htmlFor={titleFieldId}>Title</Label>
            <Input
              id={titleFieldId}
              value={title}
              maxLength={500}
              onChange={(event) => setTitle(event.target.value)}
              placeholder="Leave blank to use the title inside the document"
            />
          </div>

          <div className="space-y-2">
            <Label htmlFor={pasteFieldId}>Paste JSON instead of a file</Label>
            <Textarea
              id={pasteFieldId}
              value={pasted}
              onChange={(event) => {
                setPasted(event.target.value);
                setLocalProblem(null);
              }}
              placeholder='{"schema_version": "1", "title": "…", "chapters": [ … ]}'
              className="h-[8rem] font-mono text-xs"
              spellCheck={false}
            />
            <p className="text-muted-foreground text-xs">
              The assistant's reply, JSON only — no surrounding code fence.
            </p>
          </div>

          <div className="space-y-2">
            <p className="font-medium text-sm">No document yet?</p>
            <DocumentGuideCard guide={guide.data} isPending={guide.isPending} error={guide.error} />
          </div>
        </CollapsibleContent>
      </Collapsible>

      {localProblem ? (
        <p className="rounded-md border border-destructive/40 bg-destructive/5 p-3 text-destructive text-sm">
          {localProblem}
        </p>
      ) : null}
      {importBook.error ? <QueryError error={importBook.error} /> : null}

      <div className="flex justify-end">
        <Button type="submit" disabled={importBook.isPending}>
          {importBook.isPending ? "Uploading…" : "Import book"}
        </Button>
      </div>
    </form>
  );
}

export function BookImportDialog({
  open,
  onOpenChange,
}: {
  open: boolean;
  onOpenChange: (open: boolean) => void;
}) {
  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-h-[90vh] overflow-y-auto sm:max-w-lg">
        <DialogHeader>
          <DialogTitle className="flex items-center gap-2">
            <Upload className="size-4 text-muted-foreground" />
            Import a book
          </DialogTitle>
          <DialogDescription>
            A PDF or a book JSON document. An invalid document is refused in full and nothing is
            stored.
          </DialogDescription>
        </DialogHeader>

        <ImportForm onImported={() => onOpenChange(false)} />
      </DialogContent>
    </Dialog>
  );
}
