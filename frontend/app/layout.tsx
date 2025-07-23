import type { Metadata } from "next";
import { Inter } from "next/font/google";
import "./globals.css";
import BackendStatusChecker from "../components/BackendStatusChecker";
import Auth0Provider from "../components/Auth0Provider"; // Corrected import
import { getAuthMode } from "../lib/auth";

const inter = Inter({ subsets: ["latin"] });

export const metadata: Metadata = {
  title: "Brewdock",
  description: "The Agents Factory",
};

export default async function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  const authMode = await getAuthMode();

  if (authMode === 'auth0') {
    return (
      <html lang="en">
        <Auth0Provider>
          <body className={inter.className}>
            <BackendStatusChecker>
              {children}
            </BackendStatusChecker>
          </body>
        </Auth0Provider>
      </html>
    );
  }

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