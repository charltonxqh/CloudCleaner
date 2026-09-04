import type { Metadata } from "next";

import "./globals.css";

export const metadata: Metadata = {
  title: "CloudCleaner",
  description: "AWS lifecycle agent — finds idle resources and plans a dependency-ordered teardown.",
};

export default function RootLayout({
  children,
}: Readonly<{ children: React.ReactNode }>) {
  return (
    <html lang="en" suppressHydrationWarning>
      <body>{children}</body>
    </html>
  );
}
