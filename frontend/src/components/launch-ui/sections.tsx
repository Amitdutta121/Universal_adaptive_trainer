/**
 * Launch UI page sections (navbar, hero, items, FAQ, CTA, footer), restructured to take
 * their content as props so `app/page.tsx` owns the copy.
 */

import { Check, Menu } from "lucide-react";
import type { Route } from "next";
import Link from "next/link";
import type { ReactNode } from "react";

import { LogoGlyph } from "@/components/brand-logo";
import { Sheet, SheetContent, SheetTitle, SheetTrigger } from "@/components/ui/sheet";
import { cn } from "@/lib/utils";
import { Accordion, AccordionContent, AccordionItem, AccordionTrigger } from "./ui/accordion";
import { Button } from "./ui/button";
import { ModeToggle } from "./ui/mode-toggle";
import {
  Footer,
  FooterBottom,
  FooterColumn,
  FooterContent,
  Glow,
  Item,
  ItemDescription,
  ItemTitle,
  Mockup,
  MockupFrame,
  Section,
} from "./ui/primitives";

/** An in-page anchor such as `#faq`. */
export interface AnchorLink {
  text: string;
  href: `#${string}`;
}

/** A link to an app route, checked by Next's typed routes. */
export interface NavLink {
  text: string;
  href: Route;
}

export interface ActionLink extends NavLink {
  variant?: "default" | "glow" | "outline";
}

function ActionButtons({ actions }: { actions: ActionLink[] }) {
  return (
    <div className="relative z-10 flex flex-wrap justify-center gap-4">
      {actions.map((action) => (
        <Button key={action.href} variant={action.variant ?? "default"} size="lg" asChild>
          <Link href={action.href}>{action.text}</Link>
        </Button>
      ))}
    </div>
  );
}

export function BrandMark({ className }: { className?: string }) {
  return (
    <span
      className={cn(
        "inline-flex size-8 items-center justify-center rounded-lg bg-brand text-primary-foreground",
        className,
      )}
    >
      <LogoGlyph className="size-5" />
    </span>
  );
}

export function Navbar({
  name,
  links,
  signIn,
  cta,
}: {
  name: string;
  links: AnchorLink[];
  signIn: NavLink;
  cta: NavLink;
}) {
  return (
    <header className="sticky top-0 z-50 -mb-4 px-4 pb-4">
      <div className="fade-bottom absolute left-0 h-24 w-full bg-background/15 backdrop-blur-lg" />
      <div className="relative mx-auto max-w-container">
        <nav className="flex items-center justify-between py-4">
          <div className="flex items-center gap-8">
            <Link
              href="/"
              className="flex items-center gap-2 whitespace-nowrap font-heading font-semibold text-lg"
            >
              <BrandMark />
              {name}
            </Link>
            <div className="hidden items-center gap-6 text-sm md:flex">
              {links.map((link) => (
                <a
                  key={link.href}
                  href={link.href}
                  className="text-muted-foreground transition-colors hover:text-foreground"
                >
                  {link.text}
                </a>
              ))}
            </div>
          </div>
          <div className="flex items-center gap-4">
            <Link href={signIn.href} className="hidden text-sm md:block">
              {signIn.text}
            </Link>
            <Button asChild className="hidden sm:inline-flex">
              <Link href={cta.href}>{cta.text}</Link>
            </Button>
            <Sheet>
              <SheetTrigger asChild>
                <Button variant="ghost" size="icon" className="shrink-0 md:hidden">
                  <Menu className="size-5" />
                  <span className="sr-only">Toggle navigation menu</span>
                </Button>
              </SheetTrigger>
              <SheetContent side="right" className="p-6">
                <SheetTitle className="sr-only">Navigation menu</SheetTitle>
                <nav className="grid gap-6 font-medium text-lg">
                  <span className="font-heading font-semibold text-xl">{name}</span>
                  {[...links, signIn, cta].map((link) => (
                    <a
                      key={link.href}
                      href={link.href}
                      className="text-muted-foreground hover:text-foreground"
                    >
                      {link.text}
                    </a>
                  ))}
                </nav>
              </SheetContent>
            </Sheet>
          </div>
        </nav>
      </div>
    </header>
  );
}

export function Hero({
  badge,
  title,
  description,
  actions,
  mockup,
}: {
  badge?: ReactNode;
  title: string;
  description: string;
  actions: ActionLink[];
  mockup: ReactNode;
}) {
  return (
    <Section className="fade-bottom overflow-hidden pb-0 sm:pb-0 md:pb-0">
      <div className="mx-auto flex max-w-container flex-col gap-12 pt-16 sm:gap-24">
        <div className="flex flex-col items-center gap-6 text-center sm:gap-12">
          {badge}
          <h1 className="relative z-10 inline-block animate-appear text-balance bg-linear-to-r from-foreground to-foreground bg-clip-text font-heading font-semibold text-4xl text-transparent leading-tight drop-shadow-2xl sm:text-6xl sm:leading-tight md:text-7xl md:leading-tight dark:to-muted-foreground">
            {title}
          </h1>
          <p className="relative z-10 max-w-[740px] animate-appear text-balance font-medium text-base text-muted-foreground opacity-0 delay-100 sm:text-xl">
            {description}
          </p>
          <div className="animate-appear opacity-0 delay-300">
            <ActionButtons actions={actions} />
          </div>
          <div className="relative w-full pt-12">
            <MockupFrame className="animate-appear opacity-0 delay-700">
              <Mockup className="w-full rounded-xl border-0 bg-background/90">{mockup}</Mockup>
            </MockupFrame>
            <Glow variant="top" className="animate-appear-zoom opacity-0 delay-1000" />
          </div>
        </div>
      </div>
    </Section>
  );
}

export interface FeatureItem {
  title: string;
  description: ReactNode;
  icon: ReactNode;
}

export function Items({ id, title, items }: { id?: string; title: string; items: FeatureItem[] }) {
  return (
    <Section id={id} className="scroll-mt-16">
      <div className="mx-auto flex max-w-container flex-col items-center gap-6 sm:gap-20">
        <h2 className="max-w-[640px] text-center font-heading font-semibold text-3xl leading-tight sm:text-5xl sm:leading-tight">
          {title}
        </h2>
        <div className="grid auto-rows-fr grid-cols-2 gap-0 sm:grid-cols-3 sm:gap-4 lg:grid-cols-4">
          {items.map((item) => (
            <Item key={item.title}>
              <ItemTitle>
                <span className="flex items-center self-start text-brand">{item.icon}</span>
                {item.title}
              </ItemTitle>
              <ItemDescription>{item.description}</ItemDescription>
            </Item>
          ))}
        </div>
      </div>
    </Section>
  );
}

export interface StepItem {
  title: string;
  description: string;
}

/** Numbered workflow steps in a row, in the Items section's style. Not in upstream Launch UI. */
export function Steps({
  id,
  title,
  description,
  steps,
}: {
  id?: string;
  title: string;
  description?: string;
  steps: StepItem[];
}) {
  return (
    <Section id={id} className="scroll-mt-16">
      <div className="mx-auto flex max-w-container flex-col items-center gap-10 sm:gap-20">
        <div className="flex flex-col items-center gap-4 text-center sm:gap-6">
          <h2 className="max-w-[640px] font-heading font-semibold text-3xl leading-tight sm:text-5xl sm:leading-tight">
            {title}
          </h2>
          {description && (
            <p className="max-w-[600px] text-balance font-medium text-base text-muted-foreground sm:text-xl">
              {description}
            </p>
          )}
        </div>
        <ol className="grid w-full gap-4 sm:grid-cols-2 lg:grid-cols-4">
          {steps.map((step, index) => (
            <li key={step.title} className="glass-2 flex flex-col gap-3 rounded-xl p-6">
              <span className="font-mono text-brand text-sm">
                {String(index + 1).padStart(2, "0")}
              </span>
              <h3 className="font-heading font-semibold text-lg leading-snug">{step.title}</h3>
              <p className="text-muted-foreground text-sm leading-6">{step.description}</p>
            </li>
          ))}
        </ol>
      </div>
    </Section>
  );
}

/** Copy on one side, a framed screenshot on the other. Not in upstream Launch UI. */
export function Split({
  id,
  title,
  description,
  points,
  action,
  media,
}: {
  id?: string;
  title: string;
  description: string;
  points: string[];
  action?: ActionLink;
  media: ReactNode;
}) {
  return (
    <Section id={id} className="scroll-mt-16 overflow-hidden">
      <div className="mx-auto grid max-w-container items-center gap-12 lg:grid-cols-2 lg:gap-20">
        <div className="flex flex-col gap-6">
          <h2 className="font-heading font-semibold text-3xl leading-tight sm:text-5xl sm:leading-tight">
            {title}
          </h2>
          <p className="max-w-[540px] text-base text-muted-foreground sm:text-lg">{description}</p>
          <ul className="flex flex-col gap-3">
            {points.map((point) => (
              <li key={point} className="flex gap-3 text-sm sm:text-base">
                <Check className="mt-0.5 size-4 shrink-0 text-brand" />
                <span>{point}</span>
              </li>
            ))}
          </ul>
          {action && (
            <div>
              <Button variant={action.variant ?? "default"} size="lg" asChild>
                <Link href={action.href}>{action.text}</Link>
              </Button>
            </div>
          )}
        </div>
        <div className="relative">
          <Glow variant="center" />
          <MockupFrame>
            <Mockup className="w-full rounded-xl border-0 bg-background/90">{media}</Mockup>
          </MockupFrame>
        </div>
      </div>
    </Section>
  );
}

export interface FAQEntry {
  question: string;
  answer: ReactNode;
}

export function FAQ({ id, title, items }: { id?: string; title: string; items: FAQEntry[] }) {
  return (
    <Section id={id} className="scroll-mt-16">
      <div className="mx-auto flex max-w-container flex-col items-center gap-8">
        <h2 className="text-center font-heading font-semibold text-3xl sm:text-5xl">{title}</h2>
        <Accordion type="single" collapsible className="w-full max-w-[800px]">
          {items.map((item) => (
            <AccordionItem key={item.question} value={item.question}>
              <AccordionTrigger>{item.question}</AccordionTrigger>
              <AccordionContent>
                <p className="mb-4 max-w-[640px] text-muted-foreground">{item.answer}</p>
              </AccordionContent>
            </AccordionItem>
          ))}
        </Accordion>
      </div>
    </Section>
  );
}

export function CTA({ title, actions }: { title: string; actions: ActionLink[] }) {
  return (
    <Section className="group relative overflow-hidden">
      <div className="relative z-10 mx-auto flex max-w-container flex-col items-center gap-6 text-center sm:gap-8">
        <h2 className="max-w-[640px] font-heading font-semibold text-3xl leading-tight sm:text-5xl sm:leading-tight">
          {title}
        </h2>
        <ActionButtons actions={actions} />
      </div>
      <div className="absolute top-0 left-0 h-full w-full translate-y-[1rem] opacity-80 transition-all duration-500 ease-in-out group-hover:translate-y-[-2rem] group-hover:opacity-100">
        <Glow variant="bottom" />
      </div>
    </Section>
  );
}

export function FooterSection({
  name,
  tagline,
  columns,
}: {
  name: string;
  tagline: string;
  columns: { title: string; links: NavLink[] }[];
}) {
  return (
    <footer className="w-full bg-background px-4">
      <div className="mx-auto max-w-container">
        <Footer>
          <FooterContent>
            <FooterColumn className="col-span-2 sm:col-span-3 md:col-span-2">
              <div className="flex items-center gap-2">
                <BrandMark />
                <h3 className="font-heading font-semibold text-xl">{name}</h3>
              </div>
              <p className="max-w-[36ch] text-muted-foreground text-sm">{tagline}</p>
            </FooterColumn>
            {columns.map((column) => (
              <FooterColumn key={column.title}>
                <h3 className="pt-1 font-semibold text-base">{column.title}</h3>
                {column.links.map((link) => (
                  <Link
                    key={link.href}
                    href={link.href}
                    className="text-muted-foreground text-sm hover:text-foreground"
                  >
                    {link.text}
                  </Link>
                ))}
              </FooterColumn>
            ))}
          </FooterContent>
          <FooterBottom>
            <div>{name}</div>
            <ModeToggle />
          </FooterBottom>
        </Footer>
      </div>
    </footer>
  );
}
