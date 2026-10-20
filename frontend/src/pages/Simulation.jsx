import { useEffect, useState } from 'react';
import { api, ApiError } from '../api.js';
import { useApp } from '../context.jsx';
import { useAction, useLoad } from '../hooks.js';
import SimControls from '../components/SimControls.jsx';
import { ErrorNotice, Field, Notice, NoPlant, PageHead, SimTag, Spinner } from '../components/ui.jsx';
import { PROBLEM_LABEL, SCENARIO_LABEL, SENSOR_KEYS, SENSOR_LABEL, SENSOR_UNIT, fmtDateTime, fmtNum } from '../util.js';

const BOUNDS = { soil_moisture: [0, 100], temperature: [-10, 60], humidity: [0, 100], light: [0, 100] };

export default function Simulation() {
  const { sim, activeId, activePlant, loadSim, loadAlertCounts, bump, toast, hour12, dataVersion } = useApp();
  const meta = useLoad(() => api.get('/meta'), []);
  const latest = useLoad(() => (activeId ? api.get(`/plants/${activeId}/readings/latest`) : Promise.resolve(null)), [activeId, dataVersion]);
  const [scenario, setScenario] = useState('normal');
  const [problems, setProblems] = useState(['dry_soil', 'low_humidity']);
  const [custom, setCustom] = useState({ soil_moisture: '50', temperature: '24', humidity: '55', light: '55' });
  const [errors, setErrors] = useState({});
  const [busy, exec] = useAction();

  useEffect(() => {
    if (!sim) return;
    setScenario(sim.scenario);
    setProblems(sim.problems);
    if (sim.custom_values) setCustom(Object.fromEntries(Object.entries(sim.custom_values).map(([k, v]) => [k, String(v)])));
  }, [sim?.scenario, sim?.problems?.join(','), sim?.custom_values && JSON.stringify(sim.custom_values)]); // eslint-disable-line

  if (!activeId) return (<><PageHead title="Sensor Simulation" /><NoPlant /></>);

  const apply = () => exec(async () => {
    setErrors({});
    const body = { scenario };
    if (scenario === 'multiple') body.problems = problems;
    if (scenario === 'custom') {
      const local = {};
      SENSOR_KEYS.forEach((k) => {
        const n = Number(custom[k]);
        if (custom[k] === '' || Number.isNaN(n)) local[k] = 'Enter a number.';
        else if (n < BOUNDS[k][0] || n > BOUNDS[k][1]) local[k] = `Must be between ${BOUNDS[k][0]} and ${BOUNDS[k][1]}.`;
      });
      if (Object.keys(local).length) { setErrors(local); return; }
      body.values = Object.fromEntries(SENSOR_KEYS.map((k) => [k, Number(custom[k])]));
    }
    try {
      await api.put('/simulation/scenario', body);
      await loadSim();
      toast(`Scenario set to ${SCENARIO_LABEL[scenario]}.${sim?.state === 'running' ? '' : ' It applies to the next reading.'}`);
    } catch (e) {
      if (e instanceof ApiError && Object.keys(e.fields).length) setErrors(e.fields);
      toast(e.message, 'crit');
    }
  });

  const toggleProblem = (k) => setProblems((p) => (p.includes(k) ? p.filter((x) => x !== k) : [...p, k]));
  const state = sim?.state || 'stopped';
  const r = latest.data?.reading;

  return (
    <div className="stack">
      <PageHead title="Sensor Simulation" subtitle="The simulation runs in the Python backend. Closing this page does not stop it." />
      <section className="panel">
        <header><h2>Status</h2><SimTag /></header>
        <div className="body stack" style={{ gap: 12 }}>
          {!sim ? <Spinner /> : (
            <dl className="kv" style={{ gridTemplateColumns: 'repeat(auto-fit, minmax(170px, max-content))', columnGap: 28 }}>
              <div><dt>State</dt><dd><span className="state-chip"><span className={`dot ${state}`} aria-hidden="true" />{state.charAt(0).toUpperCase() + state.slice(1)}</span></dd></div>
              <div><dt>Scenario</dt><dd>{sim.scenario_label}</dd></div>
              <div><dt>Active plant</dt><dd>{activePlant?.name}</dd></div>
              <div><dt>Sampling interval</dt><dd>{sim.interval_seconds}s <span className="small muted">(Settings)</span></dd></div>
              <div><dt>Readings this run</dt><dd className="num">{sim.tick_count}</dd></div>
              <div><dt>Last reading</dt><dd className="num">{fmtDateTime(sim.last_reading_at, hour12)}</dd></div>
            </dl>
          )}
          {sim?.last_error && <ErrorNotice error={`Last simulation error: ${sim.last_error}`} />}
          <SimControls />
          <p className="small muted" style={{ margin: 0 }}>Reset stops the worker and returns the scenario to Normal Conditions; stored readings and alerts are kept. Generate one reading works in any state.</p>
        </div>
      </section>

      <div className="split">
        <section className="panel">
          <header><h2>Scenario</h2></header>
          <div className="body stack">
            <fieldset>
              <legend>Select scenario</legend>
              <div className="stack" style={{ gap: 6 }}>
                {(meta.data?.scenarios || Object.keys(SCENARIO_LABEL).map((key) => ({ key, label: SCENARIO_LABEL[key], description: '' }))).map((s) => (
                  <label key={s.key} className="check" style={{ alignItems: 'flex-start' }}>
                    <input type="radio" name="scenario" value={s.key} checked={scenario === s.key} onChange={() => setScenario(s.key)} style={{ marginTop: 3 }} />
                    <span><strong>{s.label}</strong><br /><span className="small muted">{s.description}</span></span>
                  </label>
                ))}
              </div>
            </fieldset>
            {scenario === 'multiple' && (
              <fieldset>
                <legend>Combine problems (choose two or more)</legend>
                <div className="row">
                  {Object.entries(PROBLEM_LABEL).map(([k, l]) => (
                    <label key={k} className="check"><input type="checkbox" checked={problems.includes(k)} onChange={() => toggleProblem(k)} />{l}</label>
                  ))}
                </div>
                {(errors.problems || problems.length < 2) && <span className="small" style={{ color: 'var(--crit)' }}>{errors.problems || 'Select at least two problems.'}</span>}
              </fieldset>
            )}
            {scenario === 'custom' && (
              <fieldset>
                <legend>Custom values (applied exactly)</legend>
                <div className="form-grid">
                  {SENSOR_KEYS.map((k) => (
                    <Field key={k} label={`${SENSOR_LABEL[k]} (${SENSOR_UNIT[k]})`} htmlFor={`c-${k}`} error={errors[k]} hint={`${BOUNDS[k][0]} to ${BOUNDS[k][1]}`}>
                      <input id={`c-${k}`} className="input" type="number" step="any" value={custom[k]} aria-invalid={!!errors[k]} onChange={(e) => setCustom((c) => ({ ...c, [k]: e.target.value }))} />
                    </Field>
                  ))}
                </div>
              </fieldset>
            )}
            <div className="row">
              <button className="btn primary" onClick={apply} disabled={busy || (scenario === 'multiple' && problems.length < 2)}>{busy ? 'Applying…' : 'Apply scenario'}</button>
              {scenario !== sim?.scenario && <span className="small muted">Not applied yet</span>}
            </div>
            <Notice>Problem scenarios move values gradually toward a target beyond the plant's warning threshold, so alerts appear after a few readings. Custom conditions take effect on the next reading.</Notice>
          </div>
        </section>
        <section className="panel">
          <header><h2>Latest generated values</h2><SimTag /></header>
          <div className="body">
            {latest.loading && !r ? <Spinner /> : !r ? <p className="muted">No readings yet for this plant.</p> : (
              <dl className="kv">
                {SENSOR_KEYS.map((k) => (<><dt key={`${k}-l`}>{SENSOR_LABEL[k]}</dt><dd key={`${k}-v`} className="num"><strong>{fmtNum(r[k])}</strong> {SENSOR_UNIT[k]}</dd></>))}
                <dt>Scenario</dt><dd>{SCENARIO_LABEL[r.scenario] || r.scenario}</dd>
                <dt>Recorded</dt><dd className="num">{fmtDateTime(r.recorded_at, hour12)}</dd>
                <dt>Source</dt><dd>{r.source} ({r.is_simulated ? 'simulated' : 'real'})</dd>
              </dl>
            )}
          </div>
        </section>
      </div>
    </div>
  );
}
