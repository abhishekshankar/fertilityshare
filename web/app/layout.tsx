import type { Metadata } from "next";
import { AuthProvider } from "./auth/context";
import { AuthNavClient } from "./auth/nav";
import "./globals.css";

export const metadata: Metadata = {
  title: "Syllabus — Your fertility learning course",
  description: "Structured, medically-grounded fertility education",
};

export default function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <html lang="en">
      <body className="min-h-screen bg-stone-50 text-stone-900 antialiased">
        <AuthProvider>
          <header className="border-b border-stone-200 bg-white/80 backdrop-blur">
            <div className="mx-auto flex h-14 max-w-4xl items-center justify-between px-4">
              <a href="/" className="font-semibold text-stone-800">
                Syllabus
              </a>
              <nav className="flex items-center gap-4 text-sm">
                <AuthNavClient />
              </nav>
            </div>
          </header>
          <main className="mx-auto max-w-4xl px-4 py-8">{children}</main>
        </AuthProvider>
      </body>
    </html>
  );
}
