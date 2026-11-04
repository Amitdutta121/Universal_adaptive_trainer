"use client";

/**
 * Drop files or a YouTube link anywhere on the Contents page: they upload at once, no dialog.
 *
 * Each file gets the same quick checks as the uploader (type, size), then starts its import
 * job; the import and the embedding after it show in the Jobs panel. A link dragged from
 * another tab is imported when it is a YouTube video; when YouTube will not give its
 * transcript, `onNeedsTranscript` opens the uploader on that link so it can be pasted.
 *
 * Listens on `window` so a drop anywhere on the page counts, including beside the table. A
 * drop the uploader dialog already handled (`defaultPrevented`) is left to it, and while
 * `disabled` drops are swallowed so the browser never opens the file in place of the app.
 */

import { Upload } from "lucide-react";
import { useEffect, useRef, useState } from "react";
import { toast } from "sonner";
import { ApiError } from "@/lib/api/client";
import { useConfig, useImportBook, useImportYoutube } from "@/lib/api/queries";
import { classifyLink } from "../source-link";
import { uploadProblem } from "./book-import-dialog";

function carriesContent(event: DragEvent) {
  const types = Array.from(event.dataTransfer?.types ?? []);
  return types.includes("Files") || types.includes("text/uri-list");
}

function errorText(error: unknown) {
  return error instanceof ApiError ? error.message : "The upload failed.";
}

export function ContentDropZone({
  disabled = false,
  onNeedsTranscript,
}: {
  disabled?: boolean;
  onNeedsTranscript: (url: string) => void;
}) {
  const config = useConfig();
  const importBook = useImportBook();
  const importVideo = useImportYoutube();
  const [active, setActive] = useState(false);
  const depth = useRef(0);

  const extensions = config.data?.supported_book_extensions ?? [".pdf"];
  const maxUploadMb = config.data?.max_book_upload_mb;

  async function uploadFile(file: File) {
    const problem = uploadProblem(file, extensions, maxUploadMb);
    if (problem) {
      toast.error(file.name, { description: problem });
      return;
    }
    const id = toast.loading(`Uploading ${file.name}…`);
    try {
      await importBook.mutateAsync({ file });
      toast.success(`Importing ${file.name}`, { id });
    } catch (error) {
      toast.error(file.name, { id, description: errorText(error) });
    }
  }

  async function importLink(url: string) {
    const parsed = classifyLink(url);
    if (parsed?.kind !== "youtube") {
      toast.error("This link cannot be imported.", {
        description: "Only YouTube links can be imported. Drop a file instead.",
      });
      return;
    }
    const id = toast.loading("Importing video…");
    try {
      const result = await importVideo.mutateAsync({ url, title: "", transcript: "" });
      toast.success(`Imported “${result.book.title}”`, { id });
    } catch (error) {
      if (error instanceof ApiError && error.code === "transcript_unavailable") {
        toast.dismiss(id);
        onNeedsTranscript(url);
        return;
      }
      toast.error("Video not imported", { id, description: errorText(error) });
    }
  }

  // Re-bound each render so the handlers see the current config and mutations.
  const handlers = useRef({ uploadFile, importLink });
  handlers.current = { uploadFile, importLink };

  useEffect(() => {
    function onDragEnter(event: DragEvent) {
      if (!carriesContent(event)) return;
      depth.current += 1;
      if (!disabled) setActive(true);
    }
    function onDragLeave(event: DragEvent) {
      if (!carriesContent(event)) return;
      depth.current = Math.max(0, depth.current - 1);
      if (depth.current === 0) setActive(false);
    }
    function onDragOver(event: DragEvent) {
      if (carriesContent(event)) event.preventDefault();
    }
    function onDrop(event: DragEvent) {
      depth.current = 0;
      setActive(false);
      if (!carriesContent(event) || event.defaultPrevented) return;
      event.preventDefault();
      if (disabled) return;
      const files = Array.from(event.dataTransfer?.files ?? []);
      if (files.length > 0) {
        void (async () => {
          for (const file of files) await handlers.current.uploadFile(file);
        })();
        return;
      }
      const url = (event.dataTransfer?.getData("text/uri-list") ?? "").split("\n")[0]?.trim();
      if (url) void handlers.current.importLink(url);
    }
    window.addEventListener("dragenter", onDragEnter);
    window.addEventListener("dragleave", onDragLeave);
    window.addEventListener("dragover", onDragOver);
    window.addEventListener("drop", onDrop);
    return () => {
      window.removeEventListener("dragenter", onDragEnter);
      window.removeEventListener("dragleave", onDragLeave);
      window.removeEventListener("dragover", onDragOver);
      window.removeEventListener("drop", onDrop);
    };
  }, [disabled]);

  if (!active) return null;
  return (
    <div
      aria-hidden
      className="pointer-events-none fixed inset-0 z-50 flex items-center justify-center bg-background/80 p-6"
    >
      <div className="flex h-full w-full flex-col items-center justify-center gap-2 rounded-xl border-2 border-primary border-dashed">
        <Upload className="size-6 text-primary" />
        <p className="font-medium text-sm">Drop to upload</p>
      </div>
    </div>
  );
}
