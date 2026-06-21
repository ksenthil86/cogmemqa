import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "CoGMEM Inspector",
  description: "Live audit dashboard for the CoGMEM-QA knowledge graph",
};

export default function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <html lang="en">
      <body className="bg-gray-950 text-gray-100 h-full">{children}</body>
    </html>
  );
}
