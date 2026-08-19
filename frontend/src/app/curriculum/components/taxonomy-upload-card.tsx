"use client";

/**
 * Upload a taxonomy document, from a saved file or from pasted text.
 *
 * Inline on the page rather than behind a dialog: uploading is what this screen
 * is for, and a professor arriving with a document in the clipboard should not
 * have to open anything first.
 *
 * Both paths end in the same multipart upload, because both are the same
 * document: a reply from an assistant is text long before it is a file.
 *
 * A rejection is shown with the backend's own message and detail — a duplicate
 * name, an unknown field, the wrong schema version — because that text is what
 * tells them what to fix. Nothing is stored on a rejection, so what they typed is
 * left exactly where it is.
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
import { useImportTaxonomy } from "@/lib/api/queries";
import type { TaxonomyDocumentGuide } from "@/lib/api/types";
import { pluralise } from "@/lib/display";
import { exceedsUploadLimit, fileFromPastedJson, jsonProblem } from "@/lib/json-document";
import { PASTED_TAXONOMY_FILENAME } from "../taxonomy-document";

type Source = "file" | "paste";

export function TaxonomyUploadCard({ guide }: { guide: TaxonomyDocumentGuide | undefined }) {
  const [source, setSource] = useState<Source>("file");
  const [file, setFile] = useState<File | null>(null);
  const [pasted, setPasted] = useState("");
  const [localProblem, setLocalProblem] = useState<string | null>(null);
  const importTaxonomy = useImportTaxonomy();

  const fileFieldId = useId();
  const pasteFieldId = useId();

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

    const problem = jsonProblem(pasted, "taxonomy document");
    if (problem) {
      setLocalProblem(problem);
      return null;
    }
    return fileFromPastedJson(pasted, PASTED_TAXONOMY_FILENAME);
  }

  async function submit(event: React.FormEvent) {
    event.preventDefault();
    setLocalProblem(null);
    importTaxonomy.reset();

    const document = documentToSend();
    if (!document) return;

    try {
      const detail = await importTaxonomy.mutateAsync({ file: document });
      toast.success(`Imported “${detail.version.label}”`, {
        description:
          `${pluralise(detail.topic_count, "topic")} and ` +
          `${pluralise(detail.subtopic_count, "subtopic")}. ` +
          "This is now the approved curriculum.",
      });
      // Only cleared on success: a refused document is still the professor's work.
      setFile(null);
      setPasted("");
      (event.target as HTMLFormElement).reset();
    } catch {
      // Rendered from `importTaxonomy.error` below, with the backend's own wording.
    }
  }

  return (
    <Card>
      <CardHeader>
        <CardTitle className="flex items-center gap-2">
          <Upload className="size-4 text-muted-foreground" />
          Upload a taxonomy document
        </CardTitle>
        <CardDescription>
          Structured taxonomy JSON only{maxUploadMb ? `, up to ${maxUploadMb} MB` : ""}. A valid
          document becomes the approved curriculum immediately; an invalid one is refused in full,
          and nothing is stored.
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
              <Label htmlFor={fileFieldId}>Taxonomy JSON document</Label>
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
                {guide ? ` (schema version ${guide.schema_version})` : ""}. The file is not
                retained, so keep your own copy.
              </p>
            </TabsContent>

            <TabsContent value="paste" className="mt-3 space-y-2">
              <Label htmlFor={pasteFieldId}>Taxonomy JSON document</Label>
              <Textarea
                id={pasteFieldId}
                value={pasted}
                onChange={(event) => {
                  setPasted(event.target.value);
                  setLocalProblem(null);
                }}
                placeholder='{"schema_version": "1", "label": "…", "topics": [ … ]}'
                className="h-[12rem] font-mono text-xs"
                spellCheck={false}
              />
              <p className="text-muted-foreground text-xs">
                Paste the assistant's reply. Include the JSON only — no surrounding code fence.
              </p>
            </TabsContent>
          </Tabs>

          <div className="flex flex-wrap items-center gap-3">
            <Button type="submit" disabled={importTaxonomy.isPending}>
              {importTaxonomy.isPending ? "Validating…" : "Upload taxonomy"}
            </Button>
            <p className="text-muted-foreground text-xs">
              The label comes from inside the document. You can rename the version afterwards.
            </p>
          </div>

          {localProblem ? (
            <p className="rounded-md border border-destructive/40 bg-destructive/5 p-3 text-destructive text-sm">
              {localProblem}
            </p>
          ) : null}
          {importTaxonomy.error ? <QueryError error={importTaxonomy.error} /> : null}
        </form>
      </CardContent>
    </Card>
  );
}
