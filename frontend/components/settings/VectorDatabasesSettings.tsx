'use client';

import React, { useState, useEffect } from 'react';
import { 
    listVectorDatabases, 
    createVectorDatabase, 
    updateVectorDatabase, 
    deleteVectorDatabase, 
    getAvailableProviders,
    VectorDatabase,
    AvailableDbConfig
} from '../../services/rag_api';

const VectorDatabasesSettings = () => {
    const [databases, setDatabases] = useState<VectorDatabase[]>([]);
    const [availableDbs, setAvailableDbs] = useState<Record<string, AvailableDbConfig>>({});
    const [isLoading, setIsLoading] = useState(true);
    const [isModalOpen, setIsModalOpen] = useState(false);
    const [editingDb, setEditingDb] = useState<Partial<VectorDatabase> | null>(null);

    useEffect(() => {
        const loadData = async () => {
            setIsLoading(true);
            try {
                const [dbs, available] = await Promise.all([
                    listVectorDatabases(),
                    getAvailableProviders()
                ]);
                setDatabases(dbs);
                setAvailableDbs(available);
            } catch (error) {
                console.error("Failed to fetch vector database data:", error);
            } finally {
                setIsLoading(false);
            }
        };
        loadData();
    }, []);

    const fetchDatabases = async () => {
        try {
            const dbs = await listVectorDatabases();
            setDatabases(dbs);
        } catch (error) {
            console.error("Failed to fetch vector databases:", error);
        }
    };

    const handleOpenModal = (db: Partial<VectorDatabase> | null = null) => {
        setEditingDb(db ? { ...db } : { name: '', provider: Object.keys(availableDbs)[0], settings: {} });
        setIsModalOpen(true);
    };

    const handleCloseModal = () => {
        setIsModalOpen(false);
        setEditingDb(null);
    };

    const handleSave = async () => {
        if (!editingDb || !editingDb.provider) return;

        try {
            if (editingDb.uuid) {
                await updateVectorDatabase(editingDb.uuid, editingDb);
            } else {
                const availableDbConfig = availableDbs[editingDb.provider];
                const newDb: Omit<VectorDatabase, 'uuid' | 'user_id' | 'created_at' | 'updated_at'> = {
                    name: editingDb.name!,
                    provider: editingDb.provider!,
                    settings: editingDb.settings!,
                    type: availableDbConfig.type,
                };
                await createVectorDatabase(newDb);
            }
            fetchDatabases();
            handleCloseModal();
        } catch (error) {
            console.error("Failed to save vector database:", error);
        }
    };

    const handleDelete = async (uuid: string) => {
        if (window.confirm('Are you sure you want to delete this vector database?')) {
            try {
                await deleteVectorDatabase(uuid);
                fetchDatabases();
            } catch (error) {
                console.error("Failed to delete vector database:", error);
            }
        }
    };
    
    const handleInputChange = (e: React.ChangeEvent<HTMLInputElement | HTMLSelectElement>) => {
        if (!editingDb) return;
        const { name, value } = e.target;

        if (name === "provider") {
            setEditingDb({ ...editingDb, [name]: value, settings: {} });
        } else {
            setEditingDb({ ...editingDb, [name]: value });
        }
    };

    const handleSettingsChange = (e: React.ChangeEvent<HTMLInputElement>) => {
        if (!editingDb) return;
        const { name, value } = e.target;
        setEditingDb({
            ...editingDb,
            settings: {
                ...editingDb.settings,
                [name]: value,
            },
        });
    };
    
    if (isLoading) {
        return <div className="p-6">Loading...</div>;
    }

    return (
        <div className="p-6">
            <div className="flex justify-between items-center mb-4">
                <h2 className="text-2xl font-bold">Vector Databases</h2>
                <button 
                    onClick={() => handleOpenModal()} 
                    className="bg-blue-500 text-white px-4 py-2 rounded hover:bg-blue-600 disabled:bg-gray-400"
                    disabled={Object.keys(availableDbs).length === 0}
                >
                    Add New
                </button>
            </div>
            <div className="bg-white shadow-md rounded-lg">
                <ul className="divide-y divide-gray-200">
                    {databases.map((db) => (
                        <li key={db.uuid} className="p-4 flex justify-between items-center">
                            <div>
                                <p className="font-semibold">{db.name} <span className="text-sm text-gray-500">({db.provider})</span></p>
                                <p className="text-xs text-gray-400">UUID: {db.uuid}</p>
                            </div>
                            <div className="space-x-2">
                                <button onClick={() => handleOpenModal(db)} className="text-sm bg-gray-200 px-3 py-1 rounded hover:bg-gray-300">Edit</button>
                                <button onClick={() => handleDelete(db.uuid)} className="text-sm bg-red-500 text-white px-3 py-1 rounded hover:bg-red-600">Delete</button>
                            </div>
                        </li>
                    ))}
                    {databases.length === 0 && <li className="p-4 text-center text-gray-500">No vector databases configured.</li>}
                </ul>
            </div>

            {isModalOpen && editingDb && editingDb.provider && (
                <div className="fixed inset-0 bg-black bg-opacity-50 flex justify-center items-center">
                    <div className="bg-white p-6 rounded-lg shadow-xl w-full max-w-md">
                        <h3 className="text-xl font-bold mb-4">{editingDb.uuid ? 'Edit' : 'Add'} Vector Database</h3>
                        
                        <div className="space-y-4">
                            <div>
                                <label className="block text-sm font-medium text-gray-700">Name</label>
                                <input type="text" name="name" value={editingDb.name || ''} onChange={handleInputChange} className="mt-1 block w-full border border-gray-300 rounded-md shadow-sm py-2 px-3"/>
                            </div>
                            <div>
                                <label className="block text-sm font-medium text-gray-700">Provider</label>
                                <select name="provider" value={editingDb.provider || ''} onChange={handleInputChange} className="mt-1 block w-full border border-gray-300 rounded-md shadow-sm py-2 px-3">
                                    {Object.keys(availableDbs).map(key => <option key={key} value={key}>{key}</option>)}
                                </select>
                            </div>

                            {Object.entries(availableDbs[editingDb.provider!].settings).map(([key, type]) => (
                                <div key={key}>
                                    <label className="block text-sm font-medium text-gray-700">{key}</label>
                                    <input type="text" name={key} value={editingDb.settings?.[key] || ''} onChange={handleSettingsChange} className="mt-1 block w-full border border-gray-300 rounded-md shadow-sm py-2 px-3"/>
                                </div>
                            ))}
                        </div>

                        <div className="mt-6 flex justify-end space-x-2">
                            <button onClick={handleCloseModal} className="bg-gray-200 px-4 py-2 rounded hover:bg-gray-300">Cancel</button>
                            <button onClick={handleSave} className="bg-blue-500 text-white px-4 py-2 rounded hover:bg-blue-600">Save</button>
                        </div>
                    </div>
                </div>
            )}
        </div>
    );
};

export default VectorDatabasesSettings; 