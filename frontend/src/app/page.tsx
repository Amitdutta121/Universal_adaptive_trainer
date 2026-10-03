/**
 * The landing page: what Adaptive Trainer is, what it will not do, and how to
 * get a fresh install running.
 *
 * Deliberately written like project documentation rather than a marketing page:
 * concrete nouns, prose instead of feature cards, sentence-case headings, stated
 * limits, and a plain screenshot. No eyebrow labels, no numbered card grid, no
 * window-chrome mockup, no gradients. If you add a section, keep it that way.
 *
 * Public (see `isLandingRoute` in `components/app-chrome.tsx`) and static except
 * for the `SetupStatus` island, which asks the backend for `/api/health`. The
 * dashboard that used to live here is now inside each course, at `/courses/{id}/dashboard`.
 *
 * The screenshot is a real capture of the Review Queue (docs/images), not a mock.
 */

import type { Metadata } from "next";
import Image from "next/image";
import Link from "next/link";
import type { ReactNode } from "react";
import { CommandBlock } from "@/components/landing/command-block";
import { SetupStatus } from "@/components/landing/setup-status";
import { Button } from "@/components/ui/button";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { SECTIONS_BY_KEY } from "@/lib/navigation";

export const metadata: Metadata = {
  title: "Adaptive Trainer",
  description:
    "Generate, review and serve adaptive practice questions from your own textbook. Runs locally.",
};

const BACKEND_CMD = `# from the repository root
py -3.12 -m venv .venv
.\\.venv\\Scripts\\python.exe -m pip install -e ".[dev]"
Copy-Item .env.example .env`;

const FRONTEND_CMD = `cd frontend
pnpm install`;

const RUN_LOCAL_BACKEND = `# terminal 1: API on :8000
.\\.venv\\Scripts\\python.exe -m app`;

const RUN_LOCAL_FRONTEND = `# terminal 2: Studio on :3000
cd frontend
pnpm run dev`;

const RUN_DOCKER = `# both services, one command
docker compose up --build`;

const LLM_ENV = `# in .env, then restart the backend
LLM_PROVIDER=openrouter
LLM_MODEL=deepseek/deepseek-chat
LLM_API_KEY=sk-or-v1-...`;

/**
 * An inline link to a Studio screen. The label comes from the nav, so it cannot
 * drift; every screen lives inside a course, so the link opens the course list.
 */
function StudioLink({ section }: { section: string }) {
  const target = SECTIONS_BY_KEY[section];
  return (
    <Link href="/courses" className="text-primary underline underline-offset-4">
      {target.label}
    </Link>
  );
}

function Row({ title, children }: { title: string; children: ReactNode }) {
  return (
    <div className="grid gap-x-10 gap-y-2 border-border border-t py-6 md:grid-cols-[13rem_minmax(0,1fr)]">
      <h3 className="font-heading font-semibold text-base tracking-[-0.01em]">{title}</h3>
      <p className="max-w-[62ch] text-[var(--ink-2)] leading-7">{children}</p>
    </div>
  );
}

function Code({ children }: { children: ReactNode }) {
  return <code className="font-mono text-[0.9em]">{children}</code>;
}

function Step({ title, children }: { title: string; children: ReactNode }) {
  return (
    <div className="flex flex-col gap-3">
      <h3 className="font-heading font-semibold text-base tracking-[-0.01em]">{title}</h3>
      {children}
    </div>
  );
}

const prose = "max-w-[62ch] text-[var(--ink-2)] text-sm leading-6";

export default function LandingPage() {
  return (
    <div className="min-h-screen bg-background">
      <header className="border-border border-b">
        <div className="mx-auto flex h-14 max-w-5xl items-center gap-6 px-5">
          <Link href="/" className="font-heading font-semibold tracking-[-0.01em]">
            Adaptive Trainer
          </Link>
          <nav className="ml-auto flex items-center gap-5 text-sm">
            <a href="#setup" className="text-muted-foreground hover:text-foreground">
              Set up
            </a>
            <Link href="/login" className="text-muted-foreground hover:text-foreground">
              Sign in
            </Link>
          </nav>
        </div>
      </header>

      <main className="mx-auto max-w-5xl px-5">
        <section className="pt-16 pb-12 sm:pt-20">
          <h1 className="max-w-[20ch] text-balance font-heading font-semibold text-[clamp(2.1rem,5vw,3.4rem)] leading-[1.06] tracking-[-0.03em]">
            Adaptive practice, built from your own textbook.
          </h1>
          <p className="mt-6 max-w-[62ch] text-[1.05rem] text-[var(--ink-2)] leading-7">
            Bring a textbook, as a PDF or structured JSON, and a topic outline. Adaptive Trainer drafts
            questions from the book, runs them through automated checks and four judge prompts, and puts each one in
            front of you to approve, edit or reject. What you approve is frozen into a set that
            students practise on without an account, and the questions they get next follow what
            they keep getting wrong.
          </p>
          <div className="mt-8 flex flex-wrap items-center gap-x-6 gap-y-3">
            <Button asChild size="lg" className="h-10 px-4">
              <Link href="/courses">Open the Studio</Link>
            </Button>
            <a href="#setup" className="text-sm underline underline-offset-4">
              Set it up locally
            </a>
          </div>

          <figure className="mt-14">
            {/* A crop at close to native scale, so the text stays readable. `unoptimized`
                because Next would otherwise resize the file and change that scale. */}
            <div className="relative aspect-[1120/720] overflow-hidden rounded-md border border-[var(--hairline-2)]">
              <Image
                src="/landing/review-queue.png"
                alt="The review queue. A Parsons question with its shuffled code blocks and the reference solution on the left, and the verdicts of the four judges on the right."
                width={1120}
                height={1065}
                priority
                unoptimized
                className="absolute top-0 left-0 h-auto w-full -translate-y-[14%]"
              />
            </div>
            <figcaption className="mt-3 max-w-[70ch] text-muted-foreground text-sm leading-6">
              The review queue, captured from the running app. On the left, a Parsons question the
              way a student sees it, beside the reference solution. On the right, the verdicts of the
              four judges.
            </figcaption>
          </figure>
        </section>

        <section className="pt-8 pb-16">
          <h2 className="mb-6 font-heading font-semibold text-2xl tracking-[-0.02em]">
            What it does
          </h2>
          <Row title="Books and the outline">
            Upload a book as a PDF or as structured JSON (chapters, sections, page numbers), and a Topic
            and Subtopic outline as JSON. Every question is tied to a passage and a subtopic. See{" "}
            <StudioLink section="books" /> and <StudioLink section="curriculum" />.
          </Row>
          <Row title="Generating questions">
            Multiple choice, Parsons and code-completion questions, drafted from a chunk you pick or
            in bulk for a whole sheet. Your review decisions feed back into the next round of
            generation. See <StudioLink section="questions" />.
          </Row>
          <Row title="Review">
            Each question gets deterministic checks, where the generated code is actually run with a
            time limit, and is then read by four advisory judges: issues, subtopic fit, difficulty
            and generatability. The judges advise and you decide. <StudioLink section="coverage" />{" "}
            lists the subtopic and difficulty cells that still have no approved question. See{" "}
            <StudioLink section="review" />.
          </Row>
          <div className="border-border border-t">
            <Row title="Classrooms">
              Freeze approved questions into a set and hand students a join link. They type a name
              and start. Mastery of each topic is tracked with Bayesian knowledge tracing after
              every answer, and the next question comes from that student's weakest subtopic.{" "}
              <StudioLink section="roster" /> shows each student's trend. See{" "}
              <StudioLink section="classrooms" />.
            </Row>
          </div>
        </section>

        <section className="pb-16">
          <h2 className="mb-4 font-heading font-semibold text-2xl tracking-[-0.02em]">Limits</h2>
          <ul className="flex max-w-[62ch] list-disc flex-col gap-2 pl-5 text-[var(--ink-2)] leading-7">
            <li>
              Each course picks a subject and the question types it uses. Some types for newer
              subjects are still marked coming soon.
            </li>
            <li>
              Books are PDF or structured JSON. A PDF with no table of contents still imports, marked
              partial, with its chapters guessed. EPUB, Markdown, plain text and HTML are refused.
              Outlines are JSON only; examples are in <Code>docs/</Code>.
            </li>
            <li>
              Generated code runs with a time limit but not in a sandbox. That is fine on your own
              machine. Do not host this for untrusted users.
            </li>
            <li>Question generation and the judges need an OpenRouter key. The rest works without one.</li>
          </ul>
        </section>

        <section id="setup" className="scroll-mt-6 border-border border-t py-16">
          <div className="grid gap-12 lg:grid-cols-[minmax(0,1fr)_17rem]">
            <div className="flex min-w-0 flex-col gap-9">
              <div className="flex flex-col gap-3">
                <h2 className="font-heading font-semibold text-2xl tracking-[-0.02em]">Set it up</h2>
                <p className={prose}>
                  You need Python 3.12 and pnpm, or Docker. The commands are PowerShell and run from
                  the repository root. <Code>docs/LOCAL_DEVELOPMENT.md</Code> has the longer notes.
                </p>
              </div>

              <Step title="Install the backend">
                <CommandBlock label="powershell" code={BACKEND_CMD} />
              </Step>

              <Step title="Install the front end">
                <CommandBlock label="powershell" code={FRONTEND_CMD} />
              </Step>

              <Step title="Start it">
                <Tabs defaultValue="local" className="gap-3">
                  <TabsList>
                    <TabsTrigger value="local">Local</TabsTrigger>
                    <TabsTrigger value="docker">Docker</TabsTrigger>
                  </TabsList>
                  <TabsContent value="local" className="flex flex-col gap-3">
                    <CommandBlock label="terminal 1" code={RUN_LOCAL_BACKEND} />
                    <CommandBlock label="terminal 2" code={RUN_LOCAL_FRONTEND} />
                  </TabsContent>
                  <TabsContent value="docker" className="flex flex-col gap-3">
                    <CommandBlock label="powershell" code={RUN_DOCKER} />
                    <p className={prose}>
                      Data lives in a Docker volume. <Code>docker compose down -v</Code> deletes it.
                    </p>
                  </TabsContent>
                </Tabs>
                <p className={prose}>
                  The Studio is at <Code>localhost:3000</Code> and the API docs are at{" "}
                  <Code>localhost:8000/docs</Code>. The status box turns green as each piece comes up.
                </p>
              </Step>

              <Step title="Sign in">
                <p className={prose}>
                  In development the backend creates one professor account: <Code>dev@local.test</Code>{" "}
                  with password <Code>devpassword123</Code>. It is never created when{" "}
                  <Code>ENVIRONMENT</Code> is anything else.
                </p>
                <div>
                  <Button asChild variant="outline" size="sm">
                    <Link href="/login">Go to sign in</Link>
                  </Button>
                </div>
              </Step>

              <Step title="Add an OpenRouter key (optional)">
                <p className={prose}>
                  Without one, everything works except generation and the judges. Never commit{" "}
                  <Code>.env</Code>.
                </p>
                <CommandBlock label=".env" code={LLM_ENV} />
              </Step>

              <p className={prose}>
                Once you are in, the sidebar runs in the order you will use it: <StudioLink section="books" />,{" "}
                <StudioLink section="curriculum" />, <StudioLink section="questions" />,{" "}
                <StudioLink section="review" />, <StudioLink section="coverage" /> and{" "}
                <StudioLink section="classrooms" />.
              </p>
            </div>

            <aside className="lg:sticky lg:top-6 lg:self-start">
              <div className="rounded-md border border-border p-4">
                <h3 className="mb-3 font-heading font-semibold text-sm">Status of this install</h3>
                <SetupStatus />
              </div>
            </aside>
          </div>
        </section>
      </main>

      <footer className="border-border border-t">
        <div className="mx-auto flex max-w-5xl flex-wrap items-center gap-x-6 gap-y-2 px-5 py-6 text-muted-foreground text-sm">
          <span>Adaptive Trainer</span>
          <Link href="/login" className="hover:text-foreground">
            Sign in
          </Link>
          <Link href="/students/join" className="hover:text-foreground">
            Student join
          </Link>
        </div>
      </footer>
    </div>
  );
}
