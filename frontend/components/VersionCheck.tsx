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

    const handleClick = () => {
        window.open('https://github.com/Itempass/mini-interns/releases', '_blank', 'noopener,noreferrer');
    };

    if (!isUpdateAvailable) {
        return null;
    }

    return (
        <button
            onClick={handleClick}
            className="ml-3 px-2 py-1 bg-amber-100 text-amber-800 text-xs font-medium rounded-full border border-amber-200 hover:bg-amber-200 transition-colors cursor-pointer"
        >
            version {latestVersion} is available!
        </button>
    );
};

export default VersionCheck; 