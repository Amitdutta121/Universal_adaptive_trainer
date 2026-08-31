"use client";

/** The persistent professor navigation, driven entirely by `lib/navigation.ts`. */

import { ChevronRight, LogOut, Moon, Sparkles, Sun, SunMoon } from "lucide-react";
import type { Route } from "next";
import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { useTheme } from "next-themes";
import { Fragment, useEffect, useState } from "react";
import { Button } from "@/components/ui/button";
import { Collapsible, CollapsibleContent, CollapsibleTrigger } from "@/components/ui/collapsible";
import {
  Sidebar,
  SidebarContent,
  SidebarFooter,
  SidebarGroup,
  SidebarGroupContent,
  SidebarGroupLabel,
  SidebarHeader,
  SidebarMenu,
  SidebarMenuButton,
  SidebarMenuItem,
  SidebarMenuSub,
  SidebarMenuSubButton,
  SidebarMenuSubItem,
  SidebarSeparator,
} from "@/components/ui/sidebar";
import { useCurrentUser, useHealth, useLogout } from "@/lib/api/queries";
import { NAV_SECTIONS, type NavSection } from "@/lib/navigation";

type AppTheme = "light" | "dark" | "system";

/** Presentational grouping only — every key still comes from the single `NAV_SECTIONS` source of truth. */
const NAV_GROUPS: ReadonlyArray<{ label: string; keys: readonly string[] }> = [
  { label: "Content Pipeline", keys: ["books", "curriculum", "questions", "generate", "review"] },
  { label: "Calibration", keys: ["instructions", "judges", "coverage"] },
  { label: "Adaptive Training", keys: ["classrooms", "roster"] },
];

function sectionsFor(keys: readonly string[]): NavSection[] {
  return keys
    .map((key) => NAV_SECTIONS.find((section) => section.key === key))
    .filter((section): section is NavSection => Boolean(section));
}

/** `true` when the current path is `section.path` or a child of it. */
function pathMatchesSection(pathname: string, path: string): boolean {
  return pathname === path || pathname.startsWith(`${path}/`);
}

/**
 * Highlight the most specific section only. `/students` is a prefix of
 * `/students/roster`, so without this the Classrooms item lights up while the
 * learner is on Roster.
 */
function isSectionActive(pathname: string, section: NavSection): boolean {
  if (!pathMatchesSection(pathname, section.path)) return false;
  return !NAV_SECTIONS.some(
    (other) =>
      other.path.length > section.path.length &&
      pathMatchesSection(pathname, other.path),
  );
}

function LlmStatus() {
  const { data, isPending, isError } = useHealth();

  if (isPending) {
    return (
      <span className="app-sidebar-status" data-tone="idle">
        <span className="app-sidebar-status-dot" />
        Checking API…
      </span>
    );
  }
  if (isError) {
    return (
      <span className="app-sidebar-status" data-tone="critical">
        <span className="app-sidebar-status-dot" />
        API unreachable
      </span>
    );
  }
  return (
    <span
      className="app-sidebar-status"
      data-tone={data.llm_configured ? "ok" : "warn"}
      title={data.llm_status}
    >
      <span className="app-sidebar-status-dot" />
      {data.llm_configured ? "LLM ready" : "LLM not configured"}
    </span>
  );
}

function ThemeSwitcher() {
  const { theme, setTheme } = useTheme();
  const [mounted, setMounted] = useState(false);

  useEffect(() => {
    setMounted(true);
  }, []);

  const activeTheme = (mounted ? (theme ?? "system") : "system") as AppTheme;

  const options: Array<{ value: AppTheme; label: string; icon: typeof Sun }> = [
    { value: "light", label: "Light", icon: Sun },
    { value: "dark", label: "Dark", icon: Moon },
    { value: "system", label: "System", icon: SunMoon },
  ];

  return (
    <div className="app-sidebar-theme">
      {options.map((option) => {
        const Icon = option.icon;
        const selected = option.value === activeTheme;
        return (
          <button
            key={option.value}
            type="button"
            aria-pressed={selected}
            title={option.label}
            className="app-sidebar-theme-option"
            data-selected={selected}
            onClick={() => setTheme(option.value)}
          >
            <Icon className="size-3.5" />
            <span className="sr-only">{option.label}</span>
          </button>
        );
      })}
    </div>
  );
}

function AccountFooter() {
  const router = useRouter();
  const currentUser = useCurrentUser();
  const logout = useLogout();

  const signOut = async () => {
    await logout.mutateAsync();
    router.push("/login" as Route);
  };

  const email = currentUser.data?.email ?? "";
  const initial = email.trim().charAt(0).toUpperCase() || "?";

  return (
    <div className="app-sidebar-account">
      <span className="app-sidebar-account-avatar" aria-hidden>
        {initial}
      </span>
      <span className="app-sidebar-account-email" title={email}>
        {email}
      </span>
      <Button
        variant="ghost"
        size="icon-sm"
        className="app-sidebar-account-signout"
        disabled={logout.isPending}
        onClick={() => void signOut()}
        title="Sign out"
      >
        <LogOut className="size-3.5" />
        <span className="sr-only">Sign out</span>
      </Button>
    </div>
  );
}

export function AppSidebar() {
  const pathname = usePathname();

  return (
    <Sidebar collapsible="icon" className="app-sidebar">
      <SidebarHeader>
        <Link href="/" className="app-sidebar-brand group-data-[collapsible=icon]:justify-center">
          <span className="app-sidebar-brand-mark">
            <Sparkles className="size-4" />
          </span>
          <span className="app-sidebar-brand-copy group-data-[collapsible=icon]:hidden">
            <span className="app-sidebar-brand-title">Adaptive Trainer</span>
            <span className="app-sidebar-brand-subtitle">Instructor Studio</span>
          </span>
        </Link>
      </SidebarHeader>

      <SidebarContent>
        {NAV_GROUPS.map((group, index) => {
          const sections = sectionsFor(group.keys);
          if (sections.length === 0) return null;
          return (
            <Fragment key={group.label}>
              {index > 0 ? <SidebarSeparator /> : null}
              <SidebarGroup>
                <SidebarGroupLabel>{group.label}</SidebarGroupLabel>
                <SidebarGroupContent>
                  <SidebarMenu>
                    {sections.map((section) => {
                      const Icon = section.icon;
                      const isActive = isSectionActive(pathname, section);

                      if (section.children?.length) {
                        return (
                          <Collapsible
                            key={section.key}
                            defaultOpen={isActive}
                            className="group/collapsible"
                          >
                            <SidebarMenuItem>
                              <CollapsibleTrigger asChild>
                                <SidebarMenuButton
                                  isActive={isActive}
                                  tooltip={section.label}
                                  className="text-[13px]"
                                >
                                  <Icon />
                                  <span>{section.label}</span>
                                  <ChevronRight className="ml-auto transition-transform group-data-[state=open]/collapsible:rotate-90" />
                                </SidebarMenuButton>
                              </CollapsibleTrigger>
                              <CollapsibleContent>
                                <SidebarMenuSub>
                                  {section.children.map((child) => {
                                    const childActive = pathname === child.path;
                                    return (
                                      <SidebarMenuSubItem key={child.key}>
                                        <SidebarMenuSubButton asChild isActive={childActive}>
                                          <Link href={child.path}>{child.label}</Link>
                                        </SidebarMenuSubButton>
                                      </SidebarMenuSubItem>
                                    );
                                  })}
                                </SidebarMenuSub>
                              </CollapsibleContent>
                            </SidebarMenuItem>
                          </Collapsible>
                        );
                      }

                      return (
                        <SidebarMenuItem key={section.key}>
                          <SidebarMenuButton
                            asChild
                            isActive={isActive}
                            tooltip={section.label}
                            className="text-[13px]"
                          >
                            <Link href={section.path}>
                              <Icon />
                              <span>{section.label}</span>
                            </Link>
                          </SidebarMenuButton>
                        </SidebarMenuItem>
                      );
                    })}
                  </SidebarMenu>
                </SidebarGroupContent>
              </SidebarGroup>
            </Fragment>
          );
        })}
      </SidebarContent>

      <SidebarFooter>
        <div className="app-sidebar-footer-stack group-data-[collapsible=icon]:hidden">
          <div className="app-sidebar-footer-row">
            <span className="app-sidebar-footer-label">Theme</span>
            <ThemeSwitcher />
          </div>
          <LlmStatus />
          <SidebarSeparator className="my-0" />
          <AccountFooter />
        </div>
      </SidebarFooter>
    </Sidebar>
  );
}
