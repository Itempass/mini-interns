import type { Metadata } from "next";
import { Inter } from "next/font/google";
import "./globals.css";
import VersionCheck from "../components/VersionCheck";

const inter = Inter({ subsets: ["latin"] });

export const metadata: Metadata = {
  title: "Mini Interns",
  description: "Manage your AI agents",
};

export default function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <html lang="en">
      <body className={inter.className}>
        <VersionCheck />
        {children}
      </body>
    </html>
  );
} 