import { useCallback, useEffect, useRef, useState } from 'react';

// Runs `fn` on mount and whenever deps change. Ignores stale responses.
export function useLoad(fn, deps) {
  const [state, setState] = useState({ data: null, error: null, loading: true });
  const seq = useRef(0);
  const run = useCallback(async (silent = false) => {
    const id = ++seq.current;
    if (!silent) setState((s) => ({ ...s, loading: true }));
    try {
      const data = await fn();
      if (id === seq.current) setState({ data, error: null, loading: false });
    } catch (e) {
      if (id === seq.current) setState((s) => ({ data: silent ? s.data : null, error: e.message, loading: false }));
    }
  }, deps); // eslint-disable-line react-hooks/exhaustive-deps
  useEffect(() => { run(false); }, [run]);
  return { ...state, reload: () => run(false) };
}

// Prevents duplicate submissions: wraps an async action with a busy flag.
export function useAction() {
  const [busy, setBusy] = useState(false);
  const exec = useCallback(async (fn) => {
    if (busy) return undefined;
    setBusy(true);
    try { return await fn(); } finally { setBusy(false); }
  }, [busy]);
  return [busy, exec];
}
