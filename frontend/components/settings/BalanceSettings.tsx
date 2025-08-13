import React, { useState, useEffect } from 'react';
import { getMe, getCostHistory, createCheckoutSession, getClientAuthMode, UserProfile, CostLogEntry } from '../../services/api';

const BalanceSettings = () => {
  const [user, setUser] = useState<UserProfile | null>(null);
  const [costHistory, setCostHistory] = useState<CostLogEntry[]>([]);
  const [totalCosts, setTotalCosts] = useState<number>(0);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [authMode, setAuthMode] = useState<'auth0' | 'password' | 'none'>('none');

  useEffect(() => {
    const fetchData = async () => {
      try {
        setLoading(true);
        const [userData, costData, mode] = await Promise.all([
          getMe(),
          getCostHistory(),
          getClientAuthMode(),
        ]);
        setUser(userData);
        setCostHistory(costData.costs);
        setTotalCosts(costData.total_costs);
        setAuthMode(mode);
        setError(null);
      } catch (err: any) {
        setError(err.message || 'Failed to fetch data.');
      } finally {
        setLoading(false);
      }
    };

    fetchData();
  }, []);

  if (loading) {
    return <div className="p-6">Loading...</div>;
  }

  if (error) {
    return <div className="p-6 text-red-500">{error}</div>;
  }

  const isAuth0 = authMode === 'auth0';

  return (
    <div className="p-6">
      <h2 className="text-2xl font-bold mb-4">Balance & Usage</h2>

      {!isAuth0 && (
        <div className="mb-4 p-3 rounded-md border bg-yellow-50 text-yellow-800 text-sm">
          Available on Hosted Version only
        </div>
      )}

      {/* Two-column header section: balance (left) and top-up (right) */}
      <div className={`mb-8 grid grid-cols-1 md:grid-cols-2 gap-4 ${!isAuth0 ? 'opacity-50' : ''}`}>
        <div className="p-4 border rounded-lg bg-gray-50">
          <h3 className="text-lg font-semibold">Current Balance</h3>
          <p className="text-3xl font-bold text-green-600">${user?.balance.toFixed(2)}</p>
        </div>
        <div className={`p-4 border rounded-lg ${!isAuth0 ? 'pointer-events-none' : ''}`}>
          <div className="flex items-center justify-between mb-2">
            <h3 className="text-lg font-semibold">Top up balance</h3>
            <div className="flex items-center gap-2 text-xs text-gray-500">
              <span aria-hidden>🔒</span>
              <span>Payments processed by</span>
              <img src="/stripe.svg" alt="Stripe" className="h-4" />
            </div>
          </div>
          <div className="flex flex-wrap gap-2 mb-3">
            {[0.5, 5, 10, 20, 50, 100].map((amt) => (
              <button
                key={amt}
                onClick={async () => {
                  try {
                    const { url } = await createCheckoutSession(amt as number);
                    window.location.href = url;
                  } catch (e: any) {
                    alert(e?.message || 'Failed to create checkout session');
                  }
                }}
                className="px-3 py-2 border rounded hover:bg-gray-50"
              >
                ${amt}
              </button>
            ))}
          </div>
          <p className="text-sm text-gray-500">You will be redirected to Stripe Checkout. After payment you’ll return here.</p>
        </div>
      </div>

      <div>
        <h3 className="text-lg font-semibold mb-2">Cost History</h3>
        <div className="overflow-x-auto border rounded-lg">
          <table className="min-w-full divide-y divide-gray-200">
            <thead className="bg-gray-50">
              <tr>
                <th scope="col" className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">Date</th>
                <th scope="col" className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">Description</th>
                <th scope="col" className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">Model</th>
                <th scope="col" className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">Tokens</th>
                <th scope="col" className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">Cost</th>
              </tr>
            </thead>
            <tbody className="bg-white divide-y divide-gray-200">
              {costHistory.length > 0 ? (
                costHistory.map((cost, index) => (
                  <tr key={index}>
                    <td className="px-6 py-4 whitespace-nowrap text-sm text-gray-500">{new Date(cost.start_time).toLocaleString()}</td>
                    <td className="px-6 py-4 whitespace-nowrap text-sm text-gray-900">{cost.step_name || 'N/A'}</td>
                    <td className="px-6 py-4 whitespace-nowrap text-sm text-gray-500">{cost.model || 'N/A'}</td>
                    <td className="px-6 py-4 whitespace-nowrap text-sm text-gray-500">{cost.total_tokens}</td>
                    <td className="px-6 py-4 whitespace-nowrap text-sm text-gray-500">${cost.total_cost?.toFixed(5)}</td>
                  </tr>
                ))
              ) : (
                <tr>
                  <td colSpan={5} className="px-6 py-4 text-center text-sm text-gray-500">No cost history available.</td>
                </tr>
              )}
            </tbody>
            <tfoot className="bg-gray-50">
              <tr>
                <td colSpan={4} className="px-6 py-3 text-right text-sm font-bold text-gray-900">Total</td>
                <td className="px-6 py-3 text-left text-sm font-bold text-gray-900">${totalCosts.toFixed(5)}</td>
              </tr>
            </tfoot>
          </table>
        </div>
      </div>
    </div>
  );
};

export default BalanceSettings; 