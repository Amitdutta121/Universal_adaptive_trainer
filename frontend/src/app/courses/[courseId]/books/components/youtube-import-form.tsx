"use client";

/**
 * Import a YouTube video as a source (Task 30): its transcript becomes timestamped chunks.
 *
 * The link alone is tried first; the backend fetches the captions. When YouTube will not give
 * them (`transcript_unavailable`), nothing was stored and a paste box appears: the professor
 * copies the transcript from YouTube's "Show transcript" panel (or a .vtt/.srt file) and sends
 * the same link again with it. The video itself is never downloaded.
 */

import { ChevronDown } from "lucide-react";
import { useId, useState } from "react";
import { toast } from "sonner";
import { QueryError } from "@/components/query-state";
import { Button } from "@/components/ui/button";
import { Collapsible, CollapsibleContent, CollapsibleTrigger } from "@/components/ui/collapsible";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import { ApiError } from "@/lib/api/client";
import { useImportYoutube } from "@/lib/api/queries";

export function YoutubeImportForm({ onImported }: { onImported: () => void }) {
  const [url, setUrl] = useState("");
  const [title, setTitle] = useState("");
  const [transcript, setTranscript] = useState("");
  const [needsPaste, setNeedsPaste] = useState(false);
  const importVideo = useImportYoutube();

  const urlFieldId = useId();
  const titleFieldId = useId();
  const transcriptFieldId = useId();

  async function submit(event: React.FormEvent) {
    event.preventDefault();
    importVideo.reset();
    try {
      const result = await importVideo.mutateAsync({
        url: url.trim(),
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
  }

  const fetchFailed =
    importVideo.error instanceof ApiError && importVideo.error.code === "transcript_unavailable";

  return (
    <form onSubmit={(event) => void submit(event)} className="min-w-0 space-y-4">
      <div className="space-y-2">
        <Label htmlFor={urlFieldId}>YouTube link</Label>
        <Input
          id={urlFieldId}
          value={url}
          required
          maxLength={500}
          placeholder="https://www.youtube.com/watch?v=…"
          onChange={(event) => {
            setUrl(event.target.value);
            setNeedsPaste(false);
            importVideo.reset();
          }}
        />
        <p className="text-muted-foreground text-xs">
          The transcript is imported with its timestamps; the video stays on YouTube.
        </p>
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
            placeholder="Leave blank to use the video’s title"
          />
        </CollapsibleContent>
      </Collapsible>

      {importVideo.error && !fetchFailed ? <QueryError error={importVideo.error} /> : null}

      <div className="flex justify-end">
        <Button type="submit" disabled={importVideo.isPending}>
          {importVideo.isPending
            ? "Importing…"
            : needsPaste
              ? "Import with transcript"
              : "Import video"}
        </Button>
      </div>
    </form>
  );
}
