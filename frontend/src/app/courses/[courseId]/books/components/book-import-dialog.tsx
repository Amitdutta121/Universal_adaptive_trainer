"use client";

/**
 * Import a book file: a modal opened from the books page header.
 *
 * One file — a PDF, DOCX or PPTX — and, under "Advanced options", a title override.
 * The accepted types and size limit come from `/api/config`, so the picker never
 * offers a file the backend would refuse.
 *
 * Submitting runs only the quick checks (type, size, whether the file opens) and
 * starts the import as a background job: the modal closes and the job's run window
 * opens (`?job=`), so parsing a long book never holds the professor here. The Jobs
 * panel announces when the book is ready, or why it was refused.
 *
 * A quick-check rejection is shown with the backend's own message and detail, because
 * that text is what tells them what to fix. Nothing is stored on a rejection, so the
 * modal stays open with what they chose.
 *
 * The second tab imports a YouTube video's transcript instead (`youtube-import-form.tsx`).
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
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { useConfig, useImportBook } from "@/lib/api/queries";
import { exceedsUploadLimit } from "@/lib/json-document";
import { titleOverride } from "../book-document";
import { YoutubeImportForm } from "./youtube-import-form";

function ImportForm({ onImported }: { onImported: () => void }) {
  const config = useConfig();
  const [file, setFile] = useState<File | null>(null);
  const [title, setTitle] = useState("");
  const [localProblem, setLocalProblem] = useState<string | null>(null);
  const importBook = useImportBook();
  const [, setJobParam] = useQueryState("job", parseAsString);

  const fileFieldId = useId();
  const titleFieldId = useId();

  const accept = config.data?.supported_book_extensions.join(",") ?? ".pdf";
  const maxUploadMb = config.data?.max_book_upload_mb;

  async function submit(event: React.FormEvent) {
    event.preventDefault();
    setLocalProblem(null);
    importBook.reset();

    if (!file) {
      setLocalProblem("Choose a book file.");
      return;
    }
    if (maxUploadMb !== undefined && exceedsUploadLimit(file.size, maxUploadMb)) {
      setLocalProblem(`This file is larger than the ${maxUploadMb} MB limit.`);
      return;
    }

    try {
      const started = await importBook.mutateAsync({ file, title: titleOverride(title) });
      // Only closed once accepted: a refused file is still the professor's choice.
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
        <CollapsibleContent className="min-w-0 space-y-2 border-t p-3">
          <Label htmlFor={titleFieldId}>Title</Label>
          <Input
            id={titleFieldId}
            value={title}
            maxLength={500}
            onChange={(event) => setTitle(event.target.value)}
            placeholder="Leave blank to use the title inside the file"
          />
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
            Import a source
          </DialogTitle>
          <DialogDescription>
            A PDF, DOCX or PPTX is split into chunks, each with its pages and headings; a YouTube
            video, by its transcript, into timed chunks. Anything that cannot be read is refused and
            nothing is stored.
          </DialogDescription>
        </DialogHeader>

        <Tabs defaultValue="file" className="min-w-0">
          <TabsList>
            <TabsTrigger value="file">File</TabsTrigger>
            <TabsTrigger value="youtube">YouTube</TabsTrigger>
          </TabsList>
          <TabsContent value="file" className="min-w-0">
            <ImportForm onImported={() => onOpenChange(false)} />
          </TabsContent>
          <TabsContent value="youtube" className="min-w-0">
            <YoutubeImportForm onImported={() => onOpenChange(false)} />
          </TabsContent>
        </Tabs>
      </DialogContent>
    </Dialog>
  );
}
