import { useState, useEffect, useRef, useCallback } from "react";

export function usePolling<T>(
  fetcher: () => Promise<T>,
  intervalMs: number,
): {
  data: T | null;
  loading: boolean;
  error: string | null;
  refetch: () => void;
} {
  const [data, setData] = useState<T | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const fetcherRef = useRef(fetcher);
  fetcherRef.current = fetcher;

  const doFetch = useCallback(async (isFirst: boolean) => {
    try {
      if (isFirst) setLoading(true);
      const result = await fetcherRef.current();
      setData(result);
      setError(null);
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      if (isFirst) setLoading(false);
    }
  }, []);

  useEffect(() => {
    doFetch(true);
    const id = setInterval(() => doFetch(false), intervalMs);
    return () => clearInterval(id);
  }, [intervalMs, doFetch]);

  return { data, loading, error, refetch: () => doFetch(false) };
}
