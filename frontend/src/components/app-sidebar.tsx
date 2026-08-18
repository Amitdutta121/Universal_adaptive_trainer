"use client";

/** The persistent professor navigation, driven entirely by `lib/navigation.ts`. */

import Link from "next/link";
import { usePathname } from "next/navigation";
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
} from "@/components/ui/sidebar";
import { useHealth } from "@/lib/api/queries";
import { NAV_SECTIONS } from "@/lib/navigation";

function LlmStatus() {
  const { data, isPending, isError } = useHealth();
  if (isPending) return <span className="app-sidebar-status">checking...</span>;
  if (isError) return <span className="app-sidebar-status">API unreachable</span>;
  return (
    <span className="app-sidebar-status" title={data.llm_status}>
      {data.llm_configured ? "LLM ready" : "LLM not configured"}
    </span>
  );
}

export function AppSidebar() {
  const pathname = usePathname();

  return (
    <Sidebar collapsible="icon" className="app-sidebar">
      <SidebarHeader>
        <div className="flex flex-col gap-0.5 px-2 py-1.5 group-data-[collapsible=icon]:hidden">
          <span className="font-semibold text-[13.5px] tracking-[-0.01em]">Adaptive Trainer</span>
          <span className="text-[11.5px] text-muted-foreground">Professor console</span>
        </div>
      </SidebarHeader>

      <SidebarContent>
        <SidebarGroup>
          <SidebarGroupLabel>Sections</SidebarGroupLabel>
          <SidebarGroupContent>
            <SidebarMenu>
              {NAV_SECTIONS.map((section) => {
                const Icon = section.icon;
                const isActive =
                  pathname === section.path || pathname.startsWith(`${section.path}/`);
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
      </SidebarContent>

      <SidebarFooter>
        <div className="px-2 pb-1 group-data-[collapsible=icon]:hidden">
          <LlmStatus />
        </div>
      </SidebarFooter>
    </Sidebar>
  );
}
