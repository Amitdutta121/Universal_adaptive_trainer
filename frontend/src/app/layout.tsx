import type { Metadata } from "next";
import { Archivo, IBM_Plex_Mono, IBM_Plex_Sans } from "next/font/google";
import { AppChrome } from "@/components/app-chrome";
import { Providers } from "@/components/providers";
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
          <AppChrome>{children}</AppChrome>
          <Toaster richColors closeButton />
        </Providers>
      </body>
    </html>
  );
}
