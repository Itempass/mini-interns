import { getAuthMode } from "../../lib/auth";
import Link from "next/link";

// Keep the original client component for the password form
import LoginPageClient from "./LoginPageClient";

export default async function LoginPage() {
  const authMode = await getAuthMode();

  if (authMode === 'auth0') {
    return (
      <div className="flex items-center justify-center min-h-screen bg-gray-50">
        <div className="w-full max-w-md p-8 space-y-8 bg-white rounded-lg shadow-md text-center">
          <h1 className="text-3xl font-bold text-gray-900">Brewdock</h1>
          <p className="mt-2 text-gray-600">The Agents Factory</p>
          <p className="mt-4 text-lg text-gray-800">Please log in to continue.</p>
          <Link
            href="/auth-client/login"
            className="inline-block w-full px-4 py-2 mt-6 text-sm font-medium text-white bg-indigo-600 border border-transparent rounded-md shadow-sm hover:bg-indigo-700 focus:outline-none focus:ring-2 focus:ring-offset-2 focus:ring-indigo-500"
          >
            Login with Auth0
          </Link>
        </div>
      </div>
    );
  }

  // If not 'auth0', render the original password login form.
  // We'll move the original component's code to LoginPageClient.tsx
  return <LoginPageClient />;
} 