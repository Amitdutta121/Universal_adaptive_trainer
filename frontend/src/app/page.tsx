/**
 * The public landing page, built on the Launch UI template (`components/launch-ui`, MIT).
 *
 * Sections: navbar, hero, how it works, features, for students, FAQ, CTA, footer.
 * Launch UI's logos, stats, testimonials and pricing sections are left out on purpose:
 * there are no real numbers, quotes or prices to put in them. Do not add placeholder ones.
 *
 * Both screenshots are real captures of the running app (docs/images), not mocks.
 * Public and static (see `isLandingRoute` in `components/app-chrome.tsx`).
 */

import {
  ChartNoAxesColumn,
  ClipboardCheck,
  Gavel,
  Grid3x3,
  Library,
  ListChecks,
  RefreshCw,
  SquareTerminal,
} from "lucide-react";
import type { Metadata } from "next";
import Image from "next/image";
import Link from "next/link";
import {
  CTA,
  FAQ,
  type FAQEntry,
  type FeatureItem,
  FooterSection,
  Hero,
  Items,
  Navbar,
  Split,
  type StepItem,
  Steps,
} from "@/components/launch-ui/sections";
import { Badge, LayoutLines } from "@/components/launch-ui/ui/primitives";

export const metadata: Metadata = {
  title: "Adaptive Trainer",
  description:
    "Turn the material you teach from into a reviewed question bank, and give every student adaptive practice.",
};

const NAME = "Adaptive Trainer";
const icon = "size-5 stroke-[1.5]";

const STEPS: StepItem[] = [
  {
    title: "Bring your material",
    description:
      "Upload what you already teach from, with a topic outline. Every question stays tied to the source it came from.",
  },
  {
    title: "Generate questions",
    description:
      "Multiple choice, Parsons and code-completion questions, drafted from one section or a whole unit at once.",
  },
  {
    title: "Review with help",
    description:
      "Generated code is run, and four judges flag issues, subtopic fit and difficulty. You approve, edit or reject.",
  },
  {
    title: "Open a classroom",
    description:
      "Freeze the approved questions into a set and share a join link. Practice adapts to each student from the first answer.",
  },
];

const FEATURES: FeatureItem[] = [
  {
    title: "Grounded in your material",
    description:
      "Questions are drafted from the sources you choose, and each one cites where it came from.",
    icon: <Library className={icon} />,
  },
  {
    title: "Your topic outline",
    description: "A Topic and Subtopic outline gives every question a place in the course.",
    icon: <ListChecks className={icon} />,
  },
  {
    title: "Three question types",
    description: "Multiple choice, Parsons problems and code completion.",
    icon: <SquareTerminal className={icon} />,
  },
  {
    title: "Code that is actually run",
    description: "Deterministic checks execute the generated code before you ever see it.",
    icon: <ClipboardCheck className={icon} />,
  },
  {
    title: "Four advisory judges",
    description:
      "Issues, subtopic fit, difficulty and generatability. The judges advise; you decide.",
    icon: <Gavel className={icon} />,
  },
  {
    title: "Learns from your reviews",
    description: "Your approvals, edits and rejections shape the next round of generation.",
    icon: <RefreshCw className={icon} />,
  },
  {
    title: "Coverage map",
    description: "See which subtopic and difficulty cells still have no approved question.",
    icon: <Grid3x3 className={icon} />,
  },
  {
    title: "Class roster",
    description: "Each student's topic mastery and trend, updated after every answer.",
    icon: <ChartNoAxesColumn className={icon} />,
  },
];

const FAQS: FAQEntry[] = [
  {
    question: "Who is Adaptive Trainer for?",
    answer:
      "Instructors who want practice questions grounded in their own course material, and the students in their classes.",
  },
  {
    question: "Does anything reach students without my approval?",
    answer:
      "No. Students only practise on questions you approved and froze into a set. Generated questions wait in your review queue until then.",
  },
  {
    question: "Do students need an account?",
    answer:
      "No. They open the classroom's join link, type a name and start. Coming back on the same browser picks up where they left off.",
  },
  {
    question: "How does it choose the next question?",
    answer:
      "Topic mastery is updated with Bayesian knowledge tracing after every answer. The next question comes from the student's weakest subtopic, at a difficulty that matches their mastery when the set has one.",
  },
  {
    question: "What material can I bring?",
    answer:
      "Today, PDF documents and structured JSON; a PDF without a table of contents still imports, with its sections guessed. Support for more kinds of material is on the way. Each course also picks a subject and the question types it uses.",
  },
];

export default function LandingPage() {
  return (
    <main className="min-h-screen w-full bg-background text-foreground">
      <LayoutLines />
      <Navbar
        name={NAME}
        links={[
          { text: "How it works", href: "#how-it-works" },
          { text: "Features", href: "#features" },
          { text: "For students", href: "#students" },
          { text: "FAQ", href: "#faq" },
        ]}
        signIn={{ text: "Sign in", href: "/login" }}
        cta={{ text: "Create an account", href: "/register" }}
      />

      <Hero
        badge={
          <Badge className="animate-appear">
            <span className="text-muted-foreground">Instructor accounts are open.</span>
            <Link href="/register" className="text-brand">
              Create one
            </Link>
          </Badge>
        }
        title="Adaptive practice, built from your own course material."
        description="Bring the material you already teach from. Adaptive Trainer turns it into a reviewed question bank, then gives each student the question they need next."
        actions={[
          { text: "Create an account", href: "/register" },
          { text: "Join a classroom", href: "/students/join", variant: "glow" },
        ]}
        mockup={
          // A crop at close to native scale, so the text stays readable. `unoptimized`
          // because Next would otherwise resize the file and change that scale.
          <div className="relative aspect-[1120/720] w-full overflow-hidden">
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
        }
      />

      <Steps
        id="how-it-works"
        title="From course material to classroom in four steps."
        description="You stay in charge of every question. The product does the drafting, checking and adapting."
        steps={STEPS}
      />

      <Items id="features" title="Everything the course needs, in one place." items={FEATURES} />

      <Split
        id="students"
        title="Practice that follows each student."
        description="Students open a join link, type their name and start. No account, nothing to install."
        points={[
          "The next question targets the subtopic they are weakest in.",
          "Every answer is scored, with feedback and the correct solution.",
          "Topic mastery updates after each answer, so progress is visible.",
          "Coming back on the same browser resumes the open session.",
        ]}
        action={{ text: "Join a classroom", href: "/students/join" }}
        media={
          <div className="relative aspect-[1036/900] w-full overflow-hidden">
            <Image
              src="/landing/student-result.png"
              alt="A student's result screen: the answer is scored, with written feedback, the change in topic mastery and the correct order of the code blocks."
              width={1036}
              height={1160}
              unoptimized
              className="absolute top-0 left-0 h-auto w-full"
            />
          </div>
        }
      />

      <FAQ id="faq" title="Questions" items={FAQS} />

      <CTA
        title="Turn your course material into adaptive practice."
        actions={[
          { text: "Create an account", href: "/register" },
          { text: "Sign in", href: "/login", variant: "glow" },
        ]}
      />

      <FooterSection
        name={NAME}
        tagline="A reviewed question bank from your own course material, and adaptive practice for every student."
        columns={[
          {
            title: "Product",
            links: [
              { text: "How it works", href: "/#how-it-works" },
              { text: "Features", href: "/#features" },
              { text: "For students", href: "/#students" },
              { text: "FAQ", href: "/#faq" },
            ],
          },
          {
            title: "Account",
            links: [
              { text: "Sign in", href: "/login" },
              { text: "Create an account", href: "/register" },
              { text: "Join a classroom", href: "/students/join" },
            ],
          },
        ]}
      />
    </main>
  );
}
