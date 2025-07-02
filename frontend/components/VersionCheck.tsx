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

            // Ignore pre-release 'latest' versions
            if (!current || !latest || latest.includes('-')) {
                return;
            }

            // Handles cases like `0.0.2-dev` or `0.0.2dev` vs `0.0.2`.
            // First, take the part before any "-", then remove any trailing letters.
            const comparableCurrent = current.split('-')[0].replace(/[a-zA-Z].*$/, '');

            // An update is available if the latest version is greater than the comparable current version,
            // or if they are equal, but the original current version was a dev build (implying it's older).
            if (latest > comparableCurrent || (latest === comparableCurrent && current.length > latest.length)) {
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