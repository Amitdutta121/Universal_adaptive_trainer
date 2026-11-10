import { describe, expect, it, vi } from "vitest";
import { attachmentFor } from "./chat-attachments";

function options(importMaterial = vi.fn().mockResolvedValue({ job_id: "book-7" })) {
  return { courseId: 3, materialExtensions: [".pdf", ".docx"], maxUploadMb: 1, importMaterial };
}

describe("attachmentFor", () => {
  it("imports a book as course material and sends a reference to it", async () => {
    const importMaterial = vi.fn().mockResolvedValue({ job_id: "book-7" });
    const file = new File(["%PDF"], "Think Python.pdf", { type: "application/pdf" });

    const result = await attachmentFor(file, options(importMaterial));

    expect(importMaterial).toHaveBeenCalledWith(file);
    expect(result).toEqual({
      type: "url",
      value: "/courses/3/books",
      mimeType: "application/pdf",
      metadata: { kind: "course_material", job_id: "book-7", filename: "Think Python.pdf" },
    });
  });

  it("refuses a book over the upload limit before uploading it", async () => {
    const importMaterial = vi.fn();
    const big = new File([new Uint8Array(2 * 1024 * 1024)], "big.pdf");
    await expect(attachmentFor(big, options(importMaterial))).rejects.toThrow("1 MB limit");
    expect(importMaterial).not.toHaveBeenCalled();
  });

  it("sends a text file as its text, and an image as the image", async () => {
    const text = await attachmentFor(new File(["Week 1"], "syllabus.md"), options());
    expect(text).toMatchObject({ type: "data", metadata: { kind: "text_file" } });
    expect(atob((text as { value: string }).value)).toBe("Week 1");

    const image = await attachmentFor(
      new File(["png"], "diagram.png", { type: "image/png" }),
      options(),
    );
    expect(image).toMatchObject({ type: "data", mimeType: "image/png" });
  });

  it("refuses other files, naming what can be attached", async () => {
    await expect(attachmentFor(new File(["x"], "setup.exe"), options())).rejects.toThrow(
      /\.pdf, \.docx, \.txt/,
    );
  });
});
