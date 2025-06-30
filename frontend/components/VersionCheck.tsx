'use client';
import React, { useState, useEffect } from 'react';
import { getVersion, getLatestVersion } from '../services/api';

const VersionCheck = () => {
    const [isUpdateAvailable, setUpdateAvailable] = useState(false);
    const [latestVersion, setLatestVersion] = useState<string | null>(null);

    useEffect(() => {
        const checkVersion = async () => {
            const current = await getVersion();
            const latest = await getLatestVersion();

            // Ignore pre-release versions (e.g., "0.0.2-rc1", "1.0.0-alpha")
            if (!latest || latest.includes('-')) {
                return;
            }

            if (current && latest > current) {
                setLatestVersion(latest);
                setUpdateAvailable(true);
            }
        };

        checkVersion();
    }, []);

    if (!isUpdateAvailable) {
        return null;
    }

    return (
        <div style={{
            backgroundColor: '#FFFBEB', // A light yellow, less intrusive than bright red/green
            color: '#92400E', // A dark amber color for text
            padding: '8px 16px',
            textAlign: 'center',
            fontSize: '14px',
            borderBottom: '1px solid #FDE68A' // A slightly darker yellow for the border
        }}>
            A new version ({latestVersion}) is available! See what's new on the{' '}
            <a 
                href="https://github.com/Itempass/mini-interns/releases" 
                target="_blank" 
                rel="noopener noreferrer"
                style={{ color: '#92400E', textDecoration: 'underline' }}
            >
                releases page
            </a>.
        </div>
    );
};

export default VersionCheck; 