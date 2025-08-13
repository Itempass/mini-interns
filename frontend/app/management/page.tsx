'use client';
import React, { useState, useEffect } from 'react';
import { getAllUsers, UserProfile, setUserBalance } from '../../services/api';
import TopBar from '../../components/TopBar';

const ManagementPage = () => {
  const [users, setUsers] = useState<UserProfile[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [editingUserId, setEditingUserId] = useState<string | null>(null);
  const [newBalance, setNewBalance] = useState<string>('');

  useEffect(() => {
    const fetchUsers = async () => {
      try {
        setLoading(true);
        const fetchedUsers = await getAllUsers();
        setUsers(fetchedUsers);
        setError(null);
      } catch (err: any) {
        setError(err.message || 'Failed to fetch users.');
      } finally {
        setLoading(false);
      }
    };

    fetchUsers();
  }, []);

  const handleSetBalance = async (userId: string) => {
    try {
      const balanceValue = parseFloat(newBalance);
      if (isNaN(balanceValue)) {
        alert('Please enter a valid number for the balance.');
        return;
      }
      const updatedUser = await setUserBalance(userId, balanceValue);
      setUsers(users.map(u => u.uuid === userId ? updatedUser : u));
      setEditingUserId(null);
      setNewBalance('');
    } catch (err) {
      alert('Failed to update balance. See console for details.');
      console.error(err);
    }
  };

  return (
    <div className="flex flex-col flex-1 bg-gray-100">
      <TopBar />
      <div className="p-8">
        <h1 className="text-2xl font-bold mb-4">User Management</h1>
        {loading && <p>Loading users...</p>}
        {error && <p className="text-red-500">{error}</p>}
        {!loading && !error && (
          <div className="overflow-x-auto border rounded-lg">
            <table className="min-w-full divide-y divide-gray-200">
              <thead className="bg-gray-50">
                <tr>
                  <th scope="col" className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">Email</th>
                  <th scope="col" className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">Balance</th>
                  <th scope="col" className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">User ID</th>
                  <th scope="col" className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">Actions</th>
                </tr>
              </thead>
              <tbody className="bg-white divide-y divide-gray-200">
                {users.map((user) => (
                  <tr key={user.uuid}>
                    <td className="px-6 py-4 whitespace-nowrap text-sm text-gray-900">{user.email || 'N/A'}</td>
                    <td className="px-6 py-4 whitespace-nowrap text-sm text-gray-500">
                      {editingUserId === user.uuid ? (
                        <input
                          type="text"
                          value={newBalance}
                          onChange={(e) => setNewBalance(e.target.value)}
                          className="border rounded px-2 py-1 w-24"
                          autoFocus
                          onKeyDown={(e) => e.key === 'Enter' && handleSetBalance(user.uuid)}
                        />
                      ) : (
                        `$${user.balance.toFixed(2)}`
                      )}
                    </td>
                    <td className="px-6 py-4 whitespace-nowrap text-sm text-gray-500">{user.uuid}</td>
                    <td className="px-6 py-4 whitespace-nowrap text-sm font-medium">
                      {editingUserId === user.uuid ? (
                        <>
                          <button onClick={() => handleSetBalance(user.uuid)} className="text-indigo-600 hover:text-indigo-900 mr-4">Save</button>
                          <button onClick={() => setEditingUserId(null)} className="text-gray-600 hover:text-gray-900">Cancel</button>
                        </>
                      ) : (
                        <button onClick={() => {
                          setEditingUserId(user.uuid);
                          setNewBalance(user.balance.toFixed(2));
                        }} className="text-indigo-600 hover:text-indigo-900">
                          Set Balance
                        </button>
                      )}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>
    </div>
  );
};

export default ManagementPage; 