import { useState } from 'react';
import { Link } from 'react-router-dom';
import { ArrowRight, Bell, ImageOff, Pencil, Play, Sprout, StepForward } from 'lucide-react';
import { api, qs } from '../api.js';
import { useApp } from '../context.jsx';
import { useLoad } from '../hooks.js';
import SensorChart from '../components/SensorChart.jsx';
import SimControls from '../components/SimControls.jsx';
import { ClassTag, Empty, ErrorNotice, HealthTag, NoPlant, PageHead, SeverityTag, SimTag, Spinner, Tag } from '../components/ui.jsx';
import { SENSOR_KEYS, SENSOR_LABEL, SHORT_UNIT, SCENARIO_LABEL, classMeta, fmtDateTime, fmtNum, timeAgo, trendMeta } from '../util.js';

function SensorCard({ parameter, status }) {
  const reading = status.latest_reading;
  const th = status.thresholds[parameter];
  const cls = status.classifications?.[parameter];
  const trend = trendMeta(status.trends[parameter].direction);
  const delta = status.trends[parameter].delta;
  const unit = SHORT_UNIT[parameter];
  const scaleMin = 0, scaleMax = parameter === 'temperature' ? 50 : 100;
  const pos = (v) => `${Math.min(100, Math.max(0, ((v - scaleMin) / (scaleMax - scaleMin)) * 100))}%`;
  const warnText = parameter === 'temperature' ? `above ${fmtNum(th.warn_high)} ${unit}`
    : parameter === 'soil_moisture' ? `below ${fmtNum(th.warn_low)} ${unit}`
    : `outside ${fmtNum(th.pref_min)}–${fmtNum(th.pref_max)} ${unit}`;
  return (
    <article className="panel sensor" aria-label={SENSOR_LABEL[parameter]}>
      <div className="top"><span className="name">{SENSOR_LABEL[parameter]}</span><SimTag /></div>
      <div className="value num">{reading ? fmtNum(reading[parameter]) : '–'}<small>{parameter === 'light' ? '% normalized' : unit}</small></div>
      <div className="row" style={{ gap: 8 }}>
        {cls ? <ClassTag code={cls.classification} /> : <Tag tone="muted">No data</Tag>}
        <span className="small muted row" style={{ gap: 3 }} title="Compared with the mean of previous readings">
          <trend.Icon size={13} aria-hidden="true" />{trend.label}{delta !== null && delta !== undefined ? ` (${delta > 0 ? '+' : ''}${fmtNum(delta)})` : ''}
        </span>
      </div>
      <div className="range-bar" aria-hidden="true">
        <div className="pref" style={{ left: pos(th.pref_min), width: `calc(${pos(th.pref_max)} - ${pos(th.pref_min)})` }} />
        {reading && <div className="marker" style={{ left: pos(reading[parameter]) }} />}
      </div>
      <dl className="meta" style={{ margin: 0 }}>
        <dt>Preferred</dt><dd><b>{fmtNum(th.pref_min)}–{fmtNum(th.pref_max)} {unit}</b></dd>
        <dt>Warning</dt><dd><b>{warnText}</b></dd>
      </dl>
      {parameter === 'light' && <span className="small muted">Normalized level, not lux.</span>}
    </article>
  );
}

export default function Dashboard() {
  const { activeId, activePlant, settings, sim, dataVersion, hour12, loadSim, loadAlertCounts, bump, toast } = useApp();
  const defaultRange = settings?.values?.default_date_range || '7d';
  const [range, setRange] = useState(null);
  const [selected, setSelected] = useState(['soil_moisture', 'temperature']);
  const period = range || defaultRange;

  const status = useLoad(() => (activeId ? api.get(`/plants/${activeId}/status`) : Promise.resolve(null)), [activeId, dataVersion]);
  const history = useLoad(() => (activeId ? api.get(`/plants/${activeId}/readings${qs({ range: period })}`) : Promise.resolve(null)), [activeId, period, dataVersion]);
  const alerts = useLoad(() => (activeId ? api.get(`/alerts${qs({ plant_id: activeId })}`) : Promise.resolve(null)), [activeId, dataVersion]);

  if (!activeId || !activePlant) return (<><PageHead title="Dashboard" /><NoPlant /></>);
  const s = status.data;
  const toggle = (k) => setSelected((cur) => (cur.includes(k) ? (cur.length > 1 ? cur.filter((x) => x !== k) : cur) : [...cur, k]));

  const quickStart = async () => {
    try {
      await api.post('/simulation/start');
      await Promise.all([loadSim(), loadAlertCounts()]);
      bump();
      toast('Simulation started! New readings are generated every 5s.');
    } catch (err) {
      toast(err.message, 'crit');
    }
  };

  const quickTick = async () => {
    try {
      await api.post('/simulation/tick');
      await Promise.all([loadSim(), loadAlertCounts()]);
      bump();
      toast('Generated 1 reading.');
    } catch (err) {
      toast(err.message, 'crit');
    }
  };

  return (
    <div className="stack">
      <PageHead title="Dashboard" subtitle="Current condition of the selected plant, from simulated sensor data.">
        <Link to="/plants" className="btn"><Sprout size={14} aria-hidden="true" />Manage plants</Link>
      </PageHead>
      <ErrorNotice error={status.error} onRetry={status.reload} />

      {s && !s.latest_reading && (
        <section className="panel" style={{ borderLeft: '4px solid var(--col-pri, #2d6a4f)' }}>
          <div className="body row" style={{ justifyContent: 'space-between', alignItems: 'center', flexWrap: 'wrap', gap: 14 }}>
            <div>
              <h3 style={{ margin: '0 0 4px', fontSize: 16 }}>🌱 Simulation is currently stopped</h3>
              <p className="muted small" style={{ margin: 0 }}>
                This is a software-simulated sensor system. No readings exist yet. Click below to start recording data:
              </p>
            </div>
            <div className="row" style={{ gap: 8 }}>
              <button className="btn primary" onClick={quickStart}><Play size={14} aria-hidden="true" />Start simulation (every 5s)</button>
              <button className="btn" onClick={quickTick}><StepForward size={14} aria-hidden="true" />Generate one reading</button>
            </div>
          </div>
        </section>
      )}

      {status.loading && !s ? <Spinner /> : s && (
        <>
          <section className="panel" aria-label="Plant overview">
            <div className="body row" style={{ alignItems: 'flex-start', gap: 14 }}>
              {activePlant.image_url
                ? <img className="plant-img" src={activePlant.image_url} alt={`${activePlant.name}`} onError={(e) => { e.currentTarget.style.display = 'none'; }} />
                : <div className="plant-img" aria-hidden="true"><ImageOff size={22} /></div>}
              <div style={{ flex: '1 1 320px', minWidth: 0 }}>
                <div className="row" style={{ gap: 8 }}>
                  <h2 style={{ fontSize: 17 }}>{activePlant.name}</h2>
                  {s.health ? <HealthTag status={s.health.status} /> : <Tag tone="muted">No readings yet</Tag>}
                </div>
                <div className="muted small" style={{ marginBottom: 6 }}><em>{activePlant.species || 'Species not set'}</em></div>
                <p style={{ margin: 0 }}>{s.health ? s.health.summary : 'No simulated readings have been recorded for this plant yet. Start the simulation or generate one reading.'}</p>
                {s.health?.status !== 'healthy' && s.health?.factors?.some((f) => f.severity) && (
                  <ul style={{ margin: '6px 0 0 18px', padding: 0 }}>
                    {s.health.factors.filter((f) => f.severity).map((f, i) => <li key={i}>{f.message}</li>)}
                  </ul>
                )}
              </div>
              <dl className="kv" style={{ flex: '0 1 260px' }}>
                <dt>Last reading</dt><dd className="num">{s.latest_reading ? `${fmtDateTime(s.latest_reading.recorded_at, hour12)} (${timeAgo(s.latest_reading.recorded_at)})` : '–'}</dd>
                <dt>Simulation</dt><dd>{sim?.state} · {SCENARIO_LABEL[sim?.scenario] || sim?.scenario}</dd>
                <dt>Source</dt><dd>Simulator <SimTag /></dd>
                <dt>Readings ({range ? period : defaultRange})</dt><dd className="num">{history.data ? history.data.count : '…'}</dd>
              </dl>
              <Link to="/plants" state={{ edit: activePlant.id }} className="btn small"><Pencil size={13} aria-hidden="true" />View / edit plant</Link>
            </div>
          </section>

          <section aria-label="Live simulated readings" className="grid-sensors">
            {SENSOR_KEYS.map((k) => <SensorCard key={k} parameter={k} status={s} />)}
          </section>

          <div className="split">
            <section className="panel" aria-label="Sensor history">
              <header>
                <h2>Sensor history</h2>
                <div className="seg" role="group" aria-label="Date range">
                  {[['today', 'Today'], ['7d', 'Last 7 Days'], ['30d', 'Last 30 Days']].map(([k, l]) => (
                    <button key={k} aria-pressed={period === k} onClick={() => setRange(k)}>{l}</button>
                  ))}
                </div>
              </header>
              <div className="body row" role="group" aria-label="Parameters shown">
                {SENSOR_KEYS.map((k) => (
                  <label key={k} className="check small"><input type="checkbox" checked={selected.includes(k)} onChange={() => toggle(k)} />{SENSOR_LABEL[k]}</label>
                ))}
              </div>
              {history.error && <div className="body"><ErrorNotice error={history.error} onRetry={history.reload} /></div>}
              {history.data && history.data.count === 0 && <Empty title="No readings in this period">Start the simulation or generate a reading to see a chart.</Empty>}
              {history.data && history.data.count > 0 && (
                <div className="stack" style={{ gap: 4, paddingBottom: 8 }}>
                  {SENSOR_KEYS.filter((k) => selected.includes(k)).map((k) => (
                    <SensorChart key={k} parameter={k} points={history.data.points} thresholds={s.thresholds} hour12={hour12} />
                  ))}
                </div>
              )}
            </section>

            <div className="stack">
              <section className="panel" aria-label="Alerts summary">
                <header><h2>Alerts</h2><Link to="/alerts" className="small">All alerts <ArrowRight size={12} aria-hidden="true" style={{ verticalAlign: -1 }} /></Link></header>
                <div className="body row" style={{ gap: 16 }}>
                  <span><strong className="num" style={{ fontSize: 20 }}>{s.alert_counts.active_critical}</strong> <span className="small muted">active critical</span></span>
                  <span><strong className="num" style={{ fontSize: 20 }}>{s.alert_counts.active_warning}</strong> <span className="small muted">active warning</span></span>
                </div>
                {alerts.data?.alerts?.length === 0 ? <Empty title="No alerts for this plant" /> : (
                  <ul className="list">
                    {(alerts.data?.alerts || []).slice(0, 5).map((a) => (
                      <li key={a.id}>
                        <div className="row" style={{ gap: 6 }}>
                          <SeverityTag severity={a.severity} />
                          <Tag tone="muted">{a.status === 'active' ? 'Active' : 'Resolved'}</Tag>
                          <span className="small muted" style={{ marginLeft: 'auto' }}>{a.is_read ? 'Read' : <strong style={{ color: 'var(--green)' }}>Unread</strong>}</span>
                        </div>
                        <div style={{ marginTop: 3 }}>{a.description}</div>
                        <div className="small muted num">{fmtDateTime(a.updated_at, hour12)}</div>
                      </li>
                    ))}
                  </ul>
                )}
              </section>
              <section className="panel" aria-label="Quick actions">
                <header><h2>Simulation &amp; quick actions</h2></header>
                <div className="body stack" style={{ gap: 10 }}>
                  <SimControls withDrySoil />
                  <div className="row">
                    <Link className="btn small" to="/simulation">Scenario controls</Link>
                    <Link className="btn small" to="/advisory">View recommendations</Link>
                    <Link className="btn small" to="/history">View history</Link>
                    <Link className="btn small" to="/plants">Manage plants</Link>
                  </div>
                </div>
              </section>
            </div>
          </div>
        </>
      )}
    </div>
  );
}
