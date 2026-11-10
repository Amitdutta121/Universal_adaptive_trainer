"use client";

/**
 * What the chat does with an attached file: paperclip, drag and drop or paste (ADR-076).
 *
 * CopilotKit shows the file as a chip and sends it with the message; `onUpload` decides what it
 * becomes before then:
 * - a book, slides or document the app can import: uploaded as course material, exactly like
 *   the Contents page's uploader, and sent as a reference (`kind: course_material`);
 * - a small text file (syllabus, CSV, a style's YAML): sent as its text (`kind: text_file`);
 * - an image: sent as the image, for a model that can see it;
 * - anything else: refused with the formats that work.
 * The backend turns the tagged parts into text the model can read (`app/agent/attachments.py`).
 */

import type { CopilotChat } from "@copilotkit/react-core/v2";
import { type ComponentProps, useMemo, useRef } from "react";
import { toast } from "sonner";
import { uploadProblem } from "@/app/courses/[courseId]/books/components/book-import-dialog";
import { useConfig, useImportBook } from "@/lib/api/queries";
import { coursePath } from "@/lib/course";

export type ChatAttachments = NonNullable<ComponentProps<typeof CopilotChat>["attachments"]>;

/** Read as text and given to the model whole (up to the backend's limit). */
export const TEXT_EXTENSIONS = [".txt", ".md", ".csv", ".json", ".yaml", ".yml", ".tex"];
const MAX_TEXT_BYTES = 2 * 1024 * 1024;
const MAX_IMAGE_BYTES = 10 * 1024 * 1024;

function extensionOf(name: string): string {
  const dot = name.lastIndexOf(".");
  return dot < 0 ? "" : name.slice(dot).toLowerCase();
}

function base64Of(file: Blob): Promise<string> {
  return new Promise((resolve, reject) => {
    const reader = new FileReader();
    reader.onload = () => resolve(String(reader.result).split(",", 2)[1] ?? "");
    reader.onerror = () => reject(reader.error ?? new Error("The file could not be read."));
    reader.readAsDataURL(file);
  });
}

/** What an attached file becomes; throws the reason it cannot be attached. */
export async function attachmentFor(
  file: File,
  {
    courseId,
    materialExtensions,
    maxUploadMb,
    importMaterial,
  }: {
    courseId: number;
    materialExtensions: string[];
    maxUploadMb?: number;
    importMaterial: (file: File) => Promise<{ job_id: string }>;
  },
): Promise<Awaited<ReturnType<NonNullable<ChatAttachments["onUpload"]>>>> {
  const extension = extensionOf(file.name);
  if (materialExtensions.includes(extension)) {
    const problem = uploadProblem(file, materialExtensions, maxUploadMb);
    if (problem) throw new Error(problem);
    const started = await importMaterial(file);
    return {
      type: "url",
      value: coursePath(courseId, "/books"),
      mimeType: file.type || "application/octet-stream",
      metadata: { kind: "course_material", job_id: started.job_id, filename: file.name },
    };
  }
  if (TEXT_EXTENSIONS.includes(extension)) {
    if (file.size > MAX_TEXT_BYTES) throw new Error("This text file is larger than 2 MB.");
    return {
      type: "data",
      value: await base64Of(file),
      mimeType: "text/plain",
      metadata: { kind: "text_file", filename: file.name },
    };
  }
  if (file.type.startsWith("image/")) {
    if (file.size > MAX_IMAGE_BYTES) throw new Error("This image is larger than 10 MB.");
    return { type: "data", value: await base64Of(file), mimeType: file.type };
  }
  const accepted = [...materialExtensions, ...TEXT_EXTENSIONS].join(", ");
  throw new Error(`This file type cannot be attached. Attach ${accepted}, or an image.`);
}

/** The chat's attachment settings for this course, shared by the side panel and the page. */
export function useChatAttachments(courseId: number): ChatAttachments {
  const config = useConfig();
  const importBook = useImportBook();
  // `onUpload` is read when a file arrives; a ref keeps it on the current config and mutation.
  const latest = useRef({ config: config.data, importBook });
  latest.current = { config: config.data, importBook };

  return useMemo<ChatAttachments>(
    () => ({
      enabled: true,
      maxConcurrentUploads: 3,
      onUpload: (file) => {
        const { config: settings, importBook: upload } = latest.current;
        return attachmentFor(file, {
          courseId,
          materialExtensions: settings?.supported_book_extensions ?? [".pdf"],
          maxUploadMb: settings?.max_book_upload_mb,
          importMaterial: (material) => upload.mutateAsync({ file: material }),
        });
      },
      onUploadFailed: (error) => toast.error(error.file.name, { description: error.message }),
    }),
    [courseId],
  );
}
