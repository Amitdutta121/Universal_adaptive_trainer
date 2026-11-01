/**
 * What a pasted link is, so the uploader knows how to import it.
 *
 * Only YouTube links can be imported today: the backend reads a video's captions and never
 * downloads the video (`app/ingestion/youtube.py`). Any other link is recognised so the
 * uploader can say why it cannot take it, rather than send it and fail. The backend checks a
 * YouTube link again (`parse_video_id`), so this only routes; it does not validate.
 */

export type SourceLink =
  | { kind: "youtube"; url: string }
  /** A web link that is not YouTube; `video` when it plainly points at a video. */
  | { kind: "other"; url: string; video: boolean }
  | { kind: "not_a_link" };

const YOUTUBE_HOSTS = ["youtube.com", "youtu.be", "youtube-nocookie.com"];
const VIDEO_HOSTS = ["vimeo.com", "loom.com", "wistia.com", "dailymotion.com", "kaltura.com"];
const VIDEO_FILE = /\.(mp4|m4v|mov|webm|mkv|avi|m3u8)$/i;

function hostIs(host: string, domains: readonly string[]) {
  return domains.some((domain) => host === domain || host.endsWith(`.${domain}`));
}

export function classifyLink(text: string): SourceLink | null {
  const trimmed = text.trim();
  if (trimmed === "") return null;
  let url: URL;
  try {
    // "youtu.be/abc" pasted without a scheme is still a link.
    url = new URL(/^[a-z][a-z0-9+.-]*:\/\//i.test(trimmed) ? trimmed : `https://${trimmed}`);
  } catch {
    return { kind: "not_a_link" };
  }
  if (!["http:", "https:"].includes(url.protocol) || !url.hostname.includes(".")) {
    return { kind: "not_a_link" };
  }
  const host = url.hostname.toLowerCase();
  if (hostIs(host, YOUTUBE_HOSTS)) return { kind: "youtube", url: url.toString() };
  return {
    kind: "other",
    url: url.toString(),
    video: hostIs(host, VIDEO_HOSTS) || VIDEO_FILE.test(url.pathname),
  };
}
