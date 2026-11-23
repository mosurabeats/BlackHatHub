import { useCallback, useEffect, useRef, useState } from "react";
import { api } from "./api";
import { useAuth } from "./auth";

/** Fetch JSON from the API; re-fetches when the path or vault state changes. */
export function useApi<T = any>(path: string | null, opts: { poll?: number } = {}) {
  const { vaultVersion } = useAuth();
  const [data, setData] = useState<T | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState<boolean>(!!path);
  const pathRef = useRef(path);
  pathRef.current = path;

  const load = useCallback(async (background = false) => {
    if (!pathRef.current) return;
    if (!background) setLoading(true);
    try {
      const d = await api<T>(pathRef.current, { background });
      setData(d);
      setError(null);
    } catch (e: any) {
      setError(e.message || "Request failed");
      if (!background) setData(null);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    load();
  }, [path, load, vaultVersion]);

  useEffect(() => {
    if (!opts.poll) return;
    const t = setInterval(() => load(true), opts.poll);
    return () => clearInterval(t);
  }, [opts.poll, load]);

  return { data, error, loading, reload: () => load(false), setData };
}
