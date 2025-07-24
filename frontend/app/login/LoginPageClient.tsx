"use client";

import { useState } from 'react';
import { useRouter } from 'next/navigation';
import { login } from '../../services/api';
import { Lock, ShieldCheck } from 'lucide-react';

export default function LoginPageClient() {
  const [password, setPassword] = useState('');
  const [error, setError] = useState('');
  const [isLoading, setIsLoading] = useState(false);
  const router = useRouter();

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setIsLoading(true);
    setError('');

    const success = await login(password);

    if (success) {
      router.push('/');
      router.refresh(); // Forces a refresh to re-evaluate middleware and fetch new data
    } else {
      setError('Incorrect password. Please try again.');
      setIsLoading(false);
    }
  };

  return (
    <div className="flex items-center justify-center min-h-screen bg-gray-100" style={{
      backgroundImage: 'radial-gradient(#E5E7EB 1px, transparent 1px)',
      backgroundSize: '24px 24px'
    }}>
      <div className="w-full max-w-sm p-8 space-y-6 bg-white border border-gray-300 rounded-2xl shadow-xl">
        <div className="text-center">
            <div className="inline-block p-3 bg-indigo-100 rounded-full">
                <div className="w-8 h-8 rounded-full border-2 border-black flex items-center justify-center bg-transparent">
                    <span className="text-black font-bold text-sm">B</span>
                </div>
            </div>
          <h2 className="mt-4 text-2xl font-bold text-gray-900">Welcome Back</h2>
          <p className="mt-2 text-sm text-gray-600">Please enter your password to access your dashboard.</p>
        </div>
        <form className="space-y-4" onSubmit={handleSubmit}>
          <div className="relative">
            <Lock className="absolute left-3 top-1/2 transform -translate-y-1/2 w-5 h-5 text-gray-400" />
            <input
              id="password"
              name="password"
              type="password"
              autoComplete="current-password"
              required
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              className="w-full px-10 py-3 text-gray-900 placeholder-gray-500 border border-gray-300 rounded-lg focus:outline-none focus:ring-2 focus:ring-indigo-500 focus:border-transparent"
              placeholder="Password"
            />
          </div>

          {error && <p className="text-xs text-center text-red-600">{error}</p>}

          <div>
            <button
              type="submit"
              disabled={isLoading}
              className="w-full px-4 py-3 text-sm font-semibold text-white bg-gray-900 border border-transparent rounded-lg shadow-sm hover:bg-black focus:outline-none focus:ring-2 focus:ring-offset-2 focus:ring-gray-900 disabled:bg-gray-500 disabled:cursor-not-allowed transition-all duration-200"
            >
              {isLoading ? 'Logging in...' : 'Login'}
            </button>
          </div>
        </form>
        <div className="text-center">
            <p className="text-xs text-gray-500 flex items-center justify-center">
                <ShieldCheck className="w-4 h-4 mr-2" />
                Your connection is secure.
            </p>
        </div>
      </div>
    </div>
  );
} 