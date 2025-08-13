import React, { useEffect, useState } from 'react';
import { getCostHistory, CostLogEntry } from '../../services/api';

const UsageHistory: React.FC = () => {
  const [costHistory, setCostHistory] = useState<CostLogEntry[]>([]);
  const [totalCosts, setTotalCosts] = useState<number>(0);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    const fetchData = async () => {
      try {
        setLoading(true);
        const costData = await getCostHistory();
        setCostHistory(costData.costs);
        setTotalCosts(costData.total_costs);
        setError(null);
      } catch (err: any) {
        setError(err.message || 'Failed to fetch usage history.');
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

  return (
    <div className="p-6">
      <h2 className="text-2xl font-bold mb-4">Usage History</h2>

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
                <td colSpan={5} className="px-6 py-4 text-center text-sm text-gray-500">No usage history available.</td>
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
  );
};

export default UsageHistory;


