import { Droplet, Pause, Play, RotateCcw, Square, StepForward } from 'lucide-react';
import { api } from '../api.js';
import { useApp } from '../context.jsx';
import { useAction } from '../hooks.js';

// Lifecycle buttons. All state lives in the backend; buttons only call the API.
export default function SimControls({ withDrySoil = false }) {
  const { sim, loadSim, loadAlertCounts, bump, toast, activePlant } = useApp();
  const [busy, exec] = useAction();
  const state = sim?.state || 'stopped';

  const run = (label, fn) => exec(async () => {
    try {
      await fn();
      await Promise.all([loadSim(), loadAlertCounts()]);
      bump();
      if (label) toast(label);
    } catch (e) {
      toast(e.message, 'crit');
    }
  });

  const disabledAll = busy || !activePlant;
  return (
    <div className="row" role="group" aria-label="Simulation controls">
      {state === 'stopped' && <button className="btn primary" disabled={disabledAll} onClick={() => run('Simulation started.', () => api.post('/simulation/start'))}><Play size={14} aria-hidden="true" />Start</button>}
      {state === 'running' && <button className="btn" disabled={busy} onClick={() => run('Simulation paused.', () => api.post('/simulation/pause'))}><Pause size={14} aria-hidden="true" />Pause</button>}
      {state === 'paused' && <button className="btn primary" disabled={busy} onClick={() => run('Simulation resumed.', () => api.post('/simulation/resume'))}><Play size={14} aria-hidden="true" />Resume</button>}
      <button className="btn" disabled={busy || state === 'stopped'} onClick={() => run('Simulation stopped.', () => api.post('/simulation/stop'))}><Square size={14} aria-hidden="true" />Stop</button>
      <button className="btn" disabled={disabledAll} onClick={() => run('One reading generated.', () => api.post('/simulation/tick'))}><StepForward size={14} aria-hidden="true" />Generate one reading</button>
      <button className="btn" disabled={busy} onClick={() => run('Simulation reset to Normal Conditions. Stored readings were kept.', () => api.post('/simulation/reset'))}><RotateCcw size={14} aria-hidden="true" />Reset</button>
      {withDrySoil && (
        <button className="btn" disabled={disabledAll} onClick={() => run('Dry Soil scenario active: soil moisture will fall gradually.', async () => {
          await api.put('/simulation/scenario', { scenario: 'dry_soil' });
          if ((await api.get('/simulation')).state === 'stopped') await api.post('/simulation/start');
        })}><Droplet size={14} aria-hidden="true" />Simulate dry soil</button>
      )}
    </div>
  );
}
