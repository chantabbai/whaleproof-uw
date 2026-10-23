import OpenFromHash from "@/components/v2/OpenFromHash";
import type { Metadata } from "next";
import { Archivo } from "next/font/google";
import Nav from "@/components/Nav";
import StatusBar from "@/components/StatusBar";
import Footer from "@/components/Footer";
import "./globals.css";

const body = Archivo({ subsets: ["latin"], axes: ["wdth"], variable: "--font-body" });

export const metadata: Metadata = {
  title: "WhaleProof",
  description: "Unusual Whales shows what the whales bought. WhaleProof keeps the few bets worth a look and checks how they did.",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en" data-theme="dark" className={body.variable} style={{ colorScheme: "dark" }}>
      <body className="min-h-screen antialiased">
        <header className="z-30 border-b md:sticky md:top-0 border-line bg-[color-mix(in_srgb,var(--sheet)_88%,transparent)] backdrop-blur-md">
          <div className="mx-auto max-w-[1180px] px-4 pt-4 md:px-8">
          <Nav />
          <StatusBar />
          </div>
        </header>
        <main className="mx-auto max-w-[1180px] px-4 pb-16 pt-8 md:px-8">{children}<OpenFromHash /></main>
        <Footer />
      </body>
    </html>
  );
}
