"use client";

/**
 * A range of a YouTube video, played through the IFrame API (Task 31).
 *
 * `startSeconds`/`endSeconds` start and stop the player, and a watcher keeps it inside the range
 * when the student seeks out of it: past the end pauses and rewinds to the start, before the start
 * jumps to it. The privacy-enhanced host (youtube-nocookie.com) is used. Below the player is what
 * is said in the range, from the transcript; nothing here describes the picture, because nothing
 * that made the block has seen it.
 */

import { RotateCcw } from "lucide-react";
import { useEffect, useRef } from "react";
import { Button } from "@/components/ui/button";
import type { VideoClipPayload } from "./types";

/** Seconds of slack before the start, so a seek landing just short of it is left alone. */
const BEFORE_SLACK = 0.5;
const WATCH_MS = 250;

/** What to do with the playhead at `time`: leave it, jump to the start, or stop at the end. */
export function rangeAction(time: number, start: number, end: number): "play" | "seek" | "stop" {
  if (time >= end) return "stop";
  if (time < start - BEFORE_SLACK) return "seek";
  return "play";
}

/** `75.4` -> `1:15`, `3725` -> `1:02:05`; the backend's chunk labels use the same form. */
export function clock(seconds: number): string {
  const total = Math.floor(seconds);
  const hours = Math.floor(total / 3600);
  const minutes = Math.floor((total % 3600) / 60);
  const secs = String(total % 60).padStart(2, "0");
  return hours ? `${hours}:${String(minutes).padStart(2, "0")}:${secs}` : `${minutes}:${secs}`;
}

// The slice of the IFrame API used here (https://developers.google.com/youtube/iframe_api_reference).
interface YTPlayer {
  getCurrentTime(): number;
  seekTo(seconds: number, allowSeekAhead: boolean): void;
  playVideo(): void;
  pauseVideo(): void;
  destroy(): void;
}
interface YTNamespace {
  Player: new (
    element: HTMLElement,
    options: {
      host?: string;
      videoId: string;
      width?: string;
      height?: string;
      playerVars?: Record<string, number | string>;
      events?: { onStateChange?: (event: { data: number }) => void };
    },
  ) => YTPlayer;
  PlayerState: { PLAYING: number };
}
declare global {
  interface Window {
    YT?: YTNamespace;
    onYouTubeIframeAPIReady?: () => void;
  }
}

let apiReady: Promise<YTNamespace> | null = null;

/** Loads the IFrame API script once per page. */
function loadYouTubeApi(): Promise<YTNamespace> {
  if (window.YT?.Player) return Promise.resolve(window.YT);
  if (apiReady) return apiReady;
  apiReady = new Promise((resolve) => {
    const previous = window.onYouTubeIframeAPIReady;
    window.onYouTubeIframeAPIReady = () => {
      previous?.();
      if (window.YT) resolve(window.YT);
    };
    const script = document.createElement("script");
    script.src = "https://www.youtube.com/iframe_api";
    script.async = true;
    document.head.appendChild(script);
  });
  return apiReady;
}

export function VideoClipBlock({ clip }: { clip: VideoClipPayload }) {
  const mount = useRef<HTMLDivElement>(null);
  const player = useRef<YTPlayer | null>(null);
  const { video_id: videoId, start, end } = clip;

  useEffect(() => {
    let cancelled = false;
    let watcher: ReturnType<typeof setInterval> | undefined;
    const stopWatching = () => {
      if (watcher !== undefined) clearInterval(watcher);
      watcher = undefined;
    };
    void loadYouTubeApi().then((YT) => {
      if (cancelled || !mount.current) return;
      const target = document.createElement("div");
      mount.current.replaceChildren(target);
      player.current = new YT.Player(target, {
        host: "https://www.youtube-nocookie.com",
        videoId,
        width: "100%",
        height: "100%",
        playerVars: {
          start: Math.floor(start),
          end: Math.ceil(end),
          rel: 0,
          playsinline: 1,
          origin: window.location.origin,
        },
        events: {
          onStateChange: ({ data }) => {
            stopWatching();
            if (data !== YT.PlayerState.PLAYING) return;
            watcher = setInterval(() => {
              const current = player.current;
              if (!current) return;
              const action = rangeAction(current.getCurrentTime(), start, end);
              if (action === "stop") {
                current.pauseVideo();
                current.seekTo(start, true);
              } else if (action === "seek") {
                current.seekTo(start, true);
              }
            }, WATCH_MS);
          },
        },
      });
    });
    return () => {
      cancelled = true;
      stopWatching();
      player.current?.destroy();
      player.current = null;
    };
  }, [videoId, start, end]);

  return (
    <figure className="space-y-2">
      <div
        ref={mount}
        className="aspect-video w-full overflow-hidden rounded-md border bg-muted"
        data-testid="video-clip-player"
      />
      <figcaption className="flex flex-wrap items-center justify-between gap-2 text-sm">
        <span className="min-w-0 text-muted-foreground">
          {clip.title ? <span className="text-foreground">{clip.title}</span> : null}
          {clip.title ? " · " : null}
          {clock(start)}–{clock(end)}
        </span>
        <Button
          type="button"
          variant="ghost"
          size="sm"
          onClick={() => {
            player.current?.seekTo(start, true);
            player.current?.playVideo();
          }}
        >
          <RotateCcw />
          Play from the start
        </Button>
      </figcaption>
      {clip.transcript ? (
        <details className="rounded-md border px-3 py-2 text-sm">
          <summary className="cursor-pointer text-muted-foreground">
            What is said in this clip
          </summary>
          <p className="mt-2 leading-relaxed">{clip.transcript}</p>
        </details>
      ) : null}
    </figure>
  );
}
