import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "Notes From Mom — little notes for living well",
  description:
    "Thoughtful notes on good food, everyday wellness, and the little things that matter.",
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html lang="en" data-scroll-behavior="smooth">
      <body suppressHydrationWarning>
        {children}
      </body>
    </html>
  );
}
