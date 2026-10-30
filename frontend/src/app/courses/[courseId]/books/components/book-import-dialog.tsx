"use client";

/**
 * Upload content: one uploader, opened from the Contents page header.
 *
 * A file — a PDF, DOCX or PPTX — is dropped on the drop zone, chosen with "Browse files", or
 * pasted anywhere in the dialog. A link is pasted in the link field (or anywhere outside a text
 * box). Whichever came last is what is uploaded; under "Advanced options" sits a title override
 * for either. The accepted types and size limit come from `/api/config`, so the uploader never
 * takes a file the backend would refuse.
 *
 * A file runs only the quick checks (type, size, whether it opens) and starts the import as a
 * background job: the modal closes and the job's run window opens (`?job=`), so parsing a long
 * book never holds the professor here. A YouTube link imports the video's transcript with its
 * timestamps; the video stays on YouTube. When YouTube will not give the captions
 * (`transcript_unavailable`) nothing is stored and a paste box asks for the transcript, sent
 * with the same link. Any other link is recognised (`source-link.ts`) and explained instead of
 * sent: the backend reads videos only from YouTube captions and fetches no file from a link.
 *
 * A refusal is shown with the backend's own message and detail, because that text is what tells
 * them what to fix. Nothing is stored on a refusal, so the modal stays open with their choice.
 */

import { ChevronDown, FileText, Link2, Upload, X } from "lucide-react";
import { parseAsString, useQueryState } from "nuqs";
import { type ClipboardEvent, type DragEvent, useId, useRef, useState } from "react";
import { toast } from "sonner";
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
import { ApiError } from "@/lib/api/client";
import { useConfig, useImportBook, useImportYoutube } from "@/lib/api/queries";
import { exceedsUploadLimit } from "@/lib/json-document";
import { formatFileSize } from "../book-display";
import { titleOverride } from "../book-document";
import { classifyLink } from "../source-link";

const FORMAT_NAMES: Record<string, string> = {
  ".pdf": "PDF",
  ".docx": "Word",
  ".pptx": "PowerPoint",
};

function extensionOf(name: string) {
  const dot = name.lastIndexOf(".");
  return dot === -1 ? "" : name.slice(dot).toLowerCase();
}

/** True when the paste or drop landed in a box the professor is typing in. */
function inTextField(target: EventTarget | null) {
  return (
    target instanceof HTMLElement &&
    (target.tagName === "TEXTAREA" || (target.tagName === "INPUT" && target.getAttribute("type") !== "file"))
  );
}

function UniversalUploader({ onImported }: { onImported: () => void }) {
  const config = useConfig();
  const importBook = useImportBook();
  const importVideo = useImportYoutube();
  const [, setJobParam] = useQueryState("job", parseAsString);
  const [file, setFile] = useState<File | null>(null);
  const [link, setLink] = useState("");
  const [title, setTitle] = useState("");
  const [transcript, setTranscript] = useState("");
  const [needsPaste, setNeedsPaste] = useState(false);
  const [dragging, setDragging] = useState(false);
  const [localProblem, setLocalProblem] = useState<string | null>(null);
  const picker = useRef<HTMLInputElement>(null);

  const fileFieldId = useId();
  const linkFieldId = useId();
  const titleFieldId = useId();
  const transcriptFieldId = useId();

  const extensions = config.data?.supported_book_extensions ?? [".pdf"];
  const maxUploadMb = config.data?.max_book_upload_mb;
  const formats = extensions.map((ext) => FORMAT_NAMES[ext] ?? ext.slice(1).toUpperCase());
  const parsed = file ? null : classifyLink(link);

  function resetResults() {
    setLocalProblem(null);
    setNeedsPaste(false);
    importBook.reset();
    importVideo.reset();
  }

  function chooseFile(next: File | null) {
    resetResults();
    setFile(next);
    if (next) setLink("");
  }

  function chooseLink(text: string) {
    resetResults();
    setLink(text);
    if (text.trim()) setFile(null);
  }

  function onDrop(event: DragEvent) {
    event.preventDefault();
    setDragging(false);
    const dropped = event.dataTransfer.files[0];
    if (dropped) chooseFile(dropped);
    else {
      // A link dragged from another tab arrives as text.
      const text = event.dataTransfer.getData("text/uri-list") || event.dataTransfer.getData("text");
      if (text) chooseLink(text.split("\n")[0]);
    }
  }

  function onPaste(event: ClipboardEvent) {
    const pasted = event.clipboardData.files[0];
    if (pasted) {
      event.preventDefault();
      chooseFile(pasted);
      return;
    }
    if (inTextField(event.target)) return;
    const text = event.clipboardData.getData("text");
    if (text.trim()) {
      event.preventDefault();
      chooseLink(text.trim());
    }
  }

  async function submit(event: React.FormEvent) {
    event.preventDefault();
    setLocalProblem(null);
    importBook.reset();

    if (file) {
      if (!extensions.includes(extensionOf(file.name))) {
        setLocalProblem(`This file type cannot be read. Upload a ${formats.join(", ")} file.`);
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
      return;
    }

    if (parsed?.kind === "youtube") {
      importVideo.reset();
      try {
        const result = await importVideo.mutateAsync({
          url: link.trim(),
          title: title.trim(),
          transcript: needsPaste ? transcript : "",
        });
        toast.success(`Imported “${result.book.title}”.`);
        onImported();
      } catch (error) {
        if (error instanceof ApiError && error.code === "transcript_unavailable") {
          setNeedsPaste(true);
        }
      }
      return;
    }

    setLocalProblem(
      parsed?.kind === "other"
        ? "This link cannot be imported."
        : parsed?.kind === "not_a_link"
          ? "That is not a link. Paste a full web address, or drop a file."
          : "Choose a file or paste a link.",
    );
  }

  const fetchFailed =
    importVideo.error instanceof ApiError && importVideo.error.code === "transcript_unavailable";
  const pending = importBook.isPending || importVideo.isPending;
  const submitLabel = pending
    ? "Uploading…"
    : file
      ? "Upload file"
      : parsed?.kind === "youtube"
        ? needsPaste
          ? "Import with transcript"
          : "Import video"
        : "Upload";

  return (
    // The whole form takes the drop, so a file let go beside the zone is not opened by the
    // browser in place of the app.
    <form
      onSubmit={(event) => void submit(event)}
      onPaste={onPaste}
      onDragOver={(event) => {
        event.preventDefault();
        setDragging(true);
      }}
      onDragLeave={(event) => {
        if (!event.currentTarget.contains(event.relatedTarget as Node | null)) setDragging(false);
      }}
      onDrop={onDrop}
      className="min-w-0 space-y-4"
    >
      <section
        aria-label="Drop a file"
        data-dragging={dragging || undefined}
        className="rounded-lg border border-dashed p-5 text-center transition-colors data-[dragging]:border-primary data-[dragging]:bg-accent/40"
      >
        <Label htmlFor={fileFieldId} className="sr-only">
          Choose a file
        </Label>
        <input
          ref={picker}
          id={fileFieldId}
          type="file"
          accept={extensions.join(",")}
          className="sr-only"
          onChange={(event) => {
            chooseFile(event.target.files?.[0] ?? null);
            event.target.value = "";
          }}
        />
        {file ? (
          <div className="flex items-center gap-3 text-left">
            <FileText className="size-5 shrink-0 text-muted-foreground" />
            <div className="min-w-0 flex-1">
              <p className="truncate font-medium text-sm">{file.name}</p>
              <p className="text-muted-foreground text-xs">{formatFileSize(file.size)}</p>
            </div>
            <Button
              type="button"
              variant="ghost"
              size="icon"
              aria-label="Remove file"
              onClick={() => chooseFile(null)}
            >
              <X />
            </Button>
          </div>
        ) : (
          <div className="space-y-2">
            <Upload className="mx-auto size-5 text-muted-foreground" />
            <p className="text-sm">
              Drop a file here, paste it, or{" "}
              <Button
                type="button"
                variant="link"
                className="h-auto p-0"
                onClick={() => picker.current?.click()}
              >
                browse files
              </Button>
            </p>
            <p className="text-muted-foreground text-xs">
              {formats.join(", ")}
              {maxUploadMb ? `, up to ${maxUploadMb} MB` : ""}
            </p>
          </div>
        )}
      </section>

      <div className="flex items-center gap-3 text-muted-foreground text-xs">
        <span className="h-px flex-1 bg-border" />
        or
        <span className="h-px flex-1 bg-border" />
      </div>

      <div className="space-y-2">
        <Label htmlFor={linkFieldId}>Paste a link</Label>
        <div className="relative">
          <Link2 className="pointer-events-none absolute top-1/2 left-3 size-4 -translate-y-1/2 text-muted-foreground" />
          <Input
            id={linkFieldId}
            value={link}
            maxLength={500}
            className="pl-9"
            placeholder="https://www.youtube.com/watch?v=…"
            onChange={(event) => chooseLink(event.target.value)}
          />
        </div>
        {parsed?.kind === "other" ? (
          <p className="text-destructive text-xs">
            {parsed.video
              ? "Only YouTube videos can be imported for now: other video links would have to be downloaded and transcribed, which is not supported yet."
              : "Only YouTube links can be imported from a link. To add a document, download it and drop the file above."}
          </p>
        ) : (
          <p className="text-muted-foreground text-xs">
            A YouTube video is imported from its transcript, with timestamps; the video stays on
            YouTube.
          </p>
        )}
      </div>

      {needsPaste ? (
        <div className="space-y-2">
          <Label htmlFor={transcriptFieldId}>Transcript</Label>
          <p className="text-muted-foreground text-xs">
            YouTube did not give us this video’s transcript. On the video’s page open “…” → Show
            transcript, copy it with its timestamps, and paste it here (a .vtt or .srt file’s text
            also works).
          </p>
          <Textarea
            id={transcriptFieldId}
            value={transcript}
            rows={8}
            required
            placeholder={"0:00\nWelcome back…"}
            onChange={(event) => setTranscript(event.target.value)}
          />
        </div>
      ) : null}

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
            placeholder="Leave blank to use the title inside the file or the video's title"
          />
        </CollapsibleContent>
      </Collapsible>

      {localProblem ? (
        <p className="rounded-md border border-destructive/40 bg-destructive/5 p-3 text-destructive text-sm">
          {localProblem}
        </p>
      ) : null}
      {importBook.error ? <QueryError error={importBook.error} /> : null}
      {importVideo.error && !fetchFailed ? <QueryError error={importVideo.error} /> : null}

      <div className="flex justify-end">
        <Button type="submit" disabled={pending || parsed?.kind === "other"}>
          {submitLabel}
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
            Upload content
          </DialogTitle>
          <DialogDescription>
            Drop or paste a book file, or paste a YouTube link. A file is split into chunks with its
            pages and headings, a video into timed chunks of its transcript. Anything that cannot be
            read is refused and nothing is stored.
          </DialogDescription>
        </DialogHeader>
        <UniversalUploader onImported={() => onOpenChange(false)} />
      </DialogContent>
    </Dialog>
  );
}
