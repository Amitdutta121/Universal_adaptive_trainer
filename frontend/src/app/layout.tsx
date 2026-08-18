import type { Metadata } from "next";
import { Archivo, IBM_Plex_Mono, IBM_Plex_Sans } from "next/font/google";
import { AppSidebar } from "@/components/app-sidebar";
import { Providers } from "@/components/providers";
import { SidebarInset, SidebarProvider } from "@/components/ui/sidebar";
import { Toaster } from "@/components/ui/sonner";
import "./globals.css";

const bodySans = IBM_Plex_Sans({
  variable: "--font-plex-sans",
  subsets: ["latin"],
  weight: ["400", "500", "600"],
});

const bodyMono = IBM_Plex_Mono({
  variable: "--font-plex-mono",
  subsets: ["latin"],
  weight: ["400", "500"],
});

const headingSans = Archivo({
  variable: "--font-archivo",
  subsets: ["latin"],
  weight: ["600", "700"],
});

export const metadata: Metadata = {
  title: "Adaptive Trainer — Professor console",
  description:
    "Generate, validate and review Python assessment questions, and follow adaptive student training.",
};

export default function RootLayout({ children }: LayoutProps<"/">) {
  return (
    <html
      lang="en"
      className={`${bodySans.variable} ${bodyMono.variable} ${headingSans.variable} h-full antialiased`}
      suppressHydrationWarning
    >
      <body className="app-body flex min-h-full flex-col">
        <Providers>
          <SidebarProvider>
            <AppSidebar />
            <SidebarInset className="app-inset">
              {/* `min-w-0`: without it this flex child refuses to shrink below the
                  width of its widest content, and a long code listing would push
                  the whole page into horizontal scroll instead of scrolling itself. */}
              <div className="app-shell mx-auto flex w-full min-w-0 max-w-7xl flex-col gap-6 p-6">
                {children}
              </div>
            </SidebarInset>
          </SidebarProvider>
          <Toaster richColors closeButton />
        </Providers>
      </body>
    </html>
  );
}
