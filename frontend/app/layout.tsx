import type { Metadata } from "next";
import { Inter } from "next/font/google";
import "./globals.css";
import BackendStatusChecker from "../components/BackendStatusChecker";

const inter = Inter({ subsets: ["latin"] });

export const metadata: Metadata = {
  title: "Brewdock",
  description: "The Agents Factory",
};

export default function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <html lang="en">
      <body className={inter.className}>
        <BackendStatusChecker>
          {children}
        </BackendStatusChecker>
      </body>
    </html>
  );
} 