import { act, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { TutorialBlockView } from "./renderer-registry";
import { clock, rangeAction } from "./video-clip-block";

const CLIP = {
  provider: "youtube",
  video_id: "AbCdEfGhIjK",
  start: 62.3,
  end: 95.7,
  title: "Loops in Python",
  transcript: "Next, the while loop. A while loop keeps running as long as its condition is true.",
};

type Options = {
  host: string;
  videoId: string;
  playerVars: Record<string, number | string>;
  events: { onStateChange: (event: { data: number }) => void };
};

class FakePlayer {
  static last: FakePlayer | null = null;
  time = 0;
  options: Options;
  seekTo = vi.fn((seconds: number) => {
    this.time = seconds;
  });
  playVideo = vi.fn();
  pauseVideo = vi.fn();
  destroy = vi.fn();
  constructor(_element: HTMLElement, options: Options) {
    this.options = options;
    FakePlayer.last = this;
  }
  getCurrentTime() {
    return this.time;
  }
}

beforeEach(() => {
  FakePlayer.last = null;
  window.YT = {
    Player: FakePlayer as never,
    PlayerState: { PLAYING: 1 },
  };
});

afterEach(() => {
  vi.useRealTimers();
});

describe("rangeAction", () => {
  it("plays inside the range, stops at the end, and jumps back from before the start", () => {
    expect(rangeAction(70, 62.3, 95.7)).toBe("play");
    expect(rangeAction(62.0, 62.3, 95.7)).toBe("play"); // within the slack
    expect(rangeAction(95.7, 62.3, 95.7)).toBe("stop");
    expect(rangeAction(300, 62.3, 95.7)).toBe("stop");
    expect(rangeAction(10, 62.3, 95.7)).toBe("seek");
  });

  it("writes times like the backend's chunk labels", () => {
    expect(clock(75.4)).toBe("1:15");
    expect(clock(3725)).toBe("1:02:05");
  });
});

describe("video_clip blocks", () => {
  it("open the player on the chosen range only, on the privacy-enhanced host", async () => {
    render(<TutorialBlockView renderer="video_clip" payload={CLIP} />);

    await waitFor(() => expect(FakePlayer.last).not.toBeNull());
    const { options } = FakePlayer.last as FakePlayer;
    expect(options.videoId).toBe("AbCdEfGhIjK");
    expect(options.host).toBe("https://www.youtube-nocookie.com");
    expect(options.playerVars).toMatchObject({ start: 62, end: 96, rel: 0 });
    expect(screen.getByText(/1:02–1:35/)).toBeInTheDocument();
    expect(screen.getByText("What is said in this clip")).toBeInTheDocument();
    expect(screen.getByText(CLIP.transcript)).toBeInTheDocument();
  });

  it("keep a seek outside the range from playing it", async () => {
    render(<TutorialBlockView renderer="video_clip" payload={CLIP} />);
    await waitFor(() => expect(FakePlayer.last).not.toBeNull());
    const player = FakePlayer.last as FakePlayer;
    vi.useFakeTimers();

    act(() => player.options.events.onStateChange({ data: 1 }));
    player.time = 120; // the student dragged past the end
    act(() => vi.advanceTimersByTime(300));
    expect(player.pauseVideo).toHaveBeenCalled();
    expect(player.seekTo).toHaveBeenLastCalledWith(62.3, true);

    player.time = 5; // ...and to before the start
    act(() => vi.advanceTimersByTime(300));
    expect(player.seekTo).toHaveBeenLastCalledWith(62.3, true);
    expect(player.time).toBe(62.3);

    player.seekTo.mockClear();
    player.time = 80;
    act(() => vi.advanceTimersByTime(1000));
    expect(player.seekTo).not.toHaveBeenCalled();
  });

  it("get the safe fallback when the payload is not a playable range", () => {
    for (const bad of [
      { ...CLIP, end: 10 },
      { ...CLIP, video_id: '"><script>' },
      { ...CLIP, provider: "vimeo" },
    ]) {
      const { unmount } = render(<TutorialBlockView renderer="video_clip" payload={bad} />);
      expect(screen.getByText(/its content is incomplete/)).toBeInTheDocument();
      unmount();
    }
  });
});
