'use client';
import { useEffect } from 'react';
import { useSearchParams, useRouter } from 'next/navigation';

export default function ManagementEntryPage() {
  const searchParams = useSearchParams();
  const router = useRouter();

  useEffect(() => {
    const userId = searchParams.get('user_id');
    if (typeof window !== 'undefined' && userId) {
      sessionStorage.setItem('admin_view_user_id', userId);
      sessionStorage.setItem('admin_view_mode', 'true');
    }
    router.replace('/workflows');
  }, [searchParams, router]);

  return null;
}


