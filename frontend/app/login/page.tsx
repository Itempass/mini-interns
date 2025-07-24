import { getAuthMode } from "../../lib/auth";
import Link from "next/link";
import { ShieldCheck } from "lucide-react";

// Keep the original client component for the password form
import LoginPageClient from "./LoginPageClient";

export default async function LoginPage() {
  const authMode = await getAuthMode();

  if (authMode === 'auth0') {
    return (
      <div className="flex items-center justify-center min-h-screen bg-gray-100" style={{
        backgroundImage: 'radial-gradient(#E5E7EB 1px, transparent 1px)',
        backgroundSize: '24px 24px'
      }}>
        <div className="w-full max-w-sm p-8 space-y-6 bg-white border border-gray-300 rounded-2xl shadow-xl text-center">
            <div className="inline-block p-3 bg-indigo-100 rounded-full">
                <div className="w-8 h-8 rounded-full border-2 border-black flex items-center justify-center bg-transparent">
                    <span className="text-black font-bold text-sm">B</span>
                </div>
            </div>
            <h2 className="mt-4 text-2xl font-bold text-gray-900">Sign in to Brewdock</h2>
            <p className="mt-2 text-sm text-gray-600">You will be redirected to our secure login provider.</p>
            <Link
                href="/auth-client/login"
                className="inline-block w-full px-4 py-3 text-sm font-semibold text-white bg-gray-900 border border-transparent rounded-lg shadow-sm hover:bg-black focus:outline-none focus:ring-2 focus:ring-offset-2 focus:ring-gray-900 transition-all duration-200"
            >
                Continue to Login
            </Link>
            <div className="text-center pt-4">
                <p className="text-xs text-gray-500 flex items-center justify-center">
                    <ShieldCheck className="w-4 h-4 mr-2" />
                    Authentication is handled by Auth0.
                </p>
            </div>
        </div>
      </div>
    );
  }

  // If not 'auth0', render the original password login form.
  return <LoginPageClient />;
} 