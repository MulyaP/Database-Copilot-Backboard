import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "Database Copilot",
  description: "AI-powered assistant for your database",
};

export default function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <html lang="en">
      <body className="bg-white text-gray-800 antialiased">
        {children}
      </body>
    </html>
  );
}
