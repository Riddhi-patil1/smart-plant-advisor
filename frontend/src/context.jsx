import { createContext, useCallback, useContext, useEffect, useMemo, useRef, useState } from 'react';
import { api } from './api.js';

const Ctx = createContext(null);
export const useApp = () => useContext(Ctx);

export function AppProvider({ children }) {
  const [plants, setPlants] = useState([]);
  const [activeId, setActiveId] = useState(null);
  const [settings, setSettings] = useState(null);
  const [sim, setSim] = useState(null);
  const [alertCounts, setAlertCounts] = useState({ active_warning: 0, active_critical: 0, unread: 0 });
  const [backendError, setBackendError] = useState(null);
  const [loaded, setLoaded] = useState(false);
  const [toasts, setToasts] = useState([]);
  // `dataVersion` increments whenever stored data changes, so pages re-fetch.
  const [dataVersion, setDataVersion] = useState(0);
  const lastReading = useRef(null);

  const toast = useCallback((message, tone = 'ok') => {
    const id = Math.random().toString(36).slice(2);
    setToasts((t) => [...t, { id, message, tone }]);
    setTimeout(() => setToasts((t) => t.filter((x) => x.id !== id)), tone === 'crit' ? 7000 : 4000);
  }, []);

  const bump = useCallback(() => setDataVersion((v) => v + 1), []);

  const loadPlants = useCallback(async () => {
    const d = await api.get('/plants');
    setPlants(d.plants);
    setActiveId(d.active_plant_id);
    return d;
  }, []);
  const loadSettings = useCallback(async () => {
    const d = await api.get('/settings');
    setSettings(d);
    return d;
  }, []);
  const loadSim = useCallback(async () => {
    const s = await api.get('/simulation');
    setSim(s);
    if (s.last_reading_at !== lastReading.current) {
      lastReading.current = s.last_reading_at;
      setDataVersion((v) => v + 1);
    }
    return s;
  }, []);
  const loadAlertCounts = useCallback(async () => {
    setAlertCounts(await api.get('/alerts/summary'));
  }, []);

  const refreshAll = useCallback(async () => {
    try {
      await Promise.all([loadPlants(), loadSettings(), loadSim(), loadAlertCounts()]);
      setBackendError(null);
    } catch (e) {
      setBackendError(e.message);
    } finally {
      setLoaded(true);
    }
  }, [loadPlants, loadSettings, loadSim, loadAlertCounts]);

  useEffect(() => { refreshAll(); }, [refreshAll]);

  // Poll the backend (the backend owns the simulation loop; the browser only observes it).
  useEffect(() => {
    const id = setInterval(async () => {
      try {
        await Promise.all([loadSim(), loadAlertCounts()]);
        setBackendError(null);
      } catch (e) {
        setBackendError(e.message);
      }
    }, 3000);
    return () => clearInterval(id);
  }, [loadSim, loadAlertCounts]);

  const selectPlant = useCallback(async (id) => {
    await api.put('/plants/active', { plant_id: Number(id) });
    setActiveId(Number(id));
    await Promise.all([loadSim(), loadAlertCounts()]);
    bump();
  }, [loadSim, loadAlertCounts, bump]);

  const activePlant = useMemo(() => plants.find((p) => p.id === activeId) || null, [plants, activeId]);
  const hour12 = settings?.values?.time_format === '12h';

  const value = {
    plants, activeId, activePlant, settings, sim, alertCounts, backendError, loaded, toasts, dataVersion, hour12,
    toast, bump, refreshAll, loadPlants, loadSettings, loadSim, loadAlertCounts, selectPlant, setToasts,
  };
  return <Ctx.Provider value={value}>{children}</Ctx.Provider>;
}
