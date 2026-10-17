import type { Metadata } from "next";
import { Inter, JetBrains_Mono, Outfit } from "next/font/google";

import { AppShell } from "@/components/layout/AppShell";

import "./globals.css";

const outfit = Outfit({ subsets: ["latin"], weight: ["300", "400", "500", "600"], variable: "--font-outfit" });
const inter = Inter({ subsets: ["latin"], weight: ["400", "500", "600"], variable: "--font-inter" });
const jetbrainsMono = JetBrains_Mono({
  subsets: ["latin"],
  weight: ["400", "500"],
  variable: "--font-jetbrains-mono",
});

export const metadata: Metadata = {
  title: "DashPilot",
  description: "Your AI co-analyst for Power BI",
};

export default function RootLayout({ children }: Readonly<{ children: React.ReactNode }>) {
  return (
    <html lang="en" className={`h-full ${outfit.variable} ${inter.variable} ${jetbrainsMono.variable}`}>
      <head>
        {/* Material Symbols is a variable icon font that next/font cannot subset, so it is linked directly. */}
        {/* eslint-disable-next-line @next/next/no-page-custom-font */}
        <link
          rel="stylesheet"
          href="https://fonts.googleapis.com/css2?family=Material+Symbols+Outlined:opsz,wght,FILL,GRAD@20..48,100..700,0..1,-50..200&display=swap"
        />
      </head>
      <body className="min-h-screen bg-shell p-0 md:p-8 font-body-md text-body-md text-on-surface antialiased selection:bg-secondary-container selection:text-on-secondary-fixed">
        <AppShell>{children}</AppShell>
      </body>
    </html>
  );
}
