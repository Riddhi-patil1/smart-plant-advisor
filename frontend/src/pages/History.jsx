import { useState } from 'react';
import { Download, FileText } from 'lucide-react';
import { api, qs } from '../api.js';
import { useApp } from '../context.jsx';
import { useLoad } from '../hooks.js';
import SensorChart from '../components/SensorChart.jsx';
import { Empty, ErrorNotice, Field, NoPlant, PageHead, SimTag, Spinner, Tag } from '../components/ui.jsx';
import { SENSOR_KEYS, SENSOR_LABEL, SENSOR_UNIT, classMeta, download, fmtDateTime, fmtNum, trendMeta } from '../util.js';

const CLASS_ORDER = ['critical_low', 'low', 'normal', 'high', 'critical_high'];
const CLASS_COLOR = { critical_low: '#a32a22', low: '#c98a1a', normal: '#5a9b73', high: '#c98a1a', critical_high: '#a32a22' };
const CLASS_NAME = { critical_low: 'Critical low', low: 'Low', normal: 'Normal', high: 'High', critical_high: 'Critical high' };

export default function History() {
  const { plants, activeId, settings, dataVersion, hour12 } = useApp();
  const [plantId, setPlantId] = useState(null);
  const [sensor, setSensor] = useState('soil_moisture');
  const [preset, setPreset] = useState(null);
  const [custom, setCustom] = useState({ from: '', to: '' });
  const [useCustom, setUseCustom] = useState(false);
  const [showReport, setShowReport] = useState(false);

  const pid = plantId ?? activeId;
  const defaultRange = settings?.values?.default_date_range || '7d';
  const rangeKey = preset || defaultRange;
  const customBad = useCustom && (!custom.from || (custom.to && custom.from > custom.to));
  const rangeQuery = useCustom ? { from: custom.from, to: custom.to } : { range: rangeKey };
  const key = JSON.stringify(rangeQuery);

  const summary = useLoad(() => (pid && !customBad ? api.get(`/analytics/summary${qs({ plant_id: pid, ...rangeQuery })}`) : Promise.resolve(null)), [pid, key, customBad, dataVersion]);
  const history = useLoad(() => (pid && !customBad ? api.get(`/plants/${pid}/readings${qs(rangeQuery)}`) : Promise.resolve(null)), [pid, key, customBad, dataVersion]);
  const status = useLoad(() => (pid ? api.get(`/plants/${pid}/status`) : Promise.resolve(null)), [pid, dataVersion]);
  const report = useLoad(() => (showReport && pid && !customBad ? api.get(`/analytics/report${qs({ plant_id: pid, ...rangeQuery })}`) : Promise.resolve(null)), [showReport, pid, key, customBad, dataVersion]);

  if (!plants.length) return (<><PageHead title="History & Analytics" /><NoPlant /></>);
  const s = summary.data;
  const plant = plants.find((p) => p.id === pid);

  return (
    <div className="stack">
      <PageHead title="History & Analytics" subtitle="Stored simulated readings, alerts and recommendations for one plant at a time." />
      <section className="panel">
        <div className="body form-grid" role="search" aria-label="Analytics filters">
          <Field label="Plant" htmlFor="h-plant"><select id="h-plant" className="input" value={pid ?? ''} onChange={(e) => setPlantId(Number(e.target.value))}>{plants.map((p) => <option key={p.id} value={p.id}>{p.name}</option>)}</select></Field>
          <Field label="Sensor" htmlFor="h-sensor"><select id="h-sensor" className="input" value={sensor} onChange={(e) => setSensor(e.target.value)}>{SENSOR_KEYS.map((k) => <option key={k} value={k}>{SENSOR_LABEL[k]}</option>)}</select></Field>
          <div className="field"><span className="lbl">Period</span>
            <div className="seg" role="group" aria-label="Period">
              {[['today', 'Today'], ['7d', 'Last 7 Days'], ['30d', 'Last 30 Days']].map(([k, l]) => (
                <button key={k} type="button" aria-pressed={!useCustom && rangeKey === k} onClick={() => { setUseCustom(false); setPreset(k); }}>{l}</button>
              ))}
              <button type="button" aria-pressed={useCustom} onClick={() => setUseCustom(true)}>Custom</button>
            </div>
          </div>
          {useCustom && (
            <>
              <Field label="From" htmlFor="h-from" error={useCustom && !custom.from ? 'Choose a start date.' : null}><input id="h-from" type="date" className="input" value={custom.from} onChange={(e) => setCustom({ ...custom, from: e.target.value })} /></Field>
              <Field label="To (optional)" htmlFor="h-to" error={custom.from && custom.to && custom.from > custom.to ? 'End date must not be before the start date.' : null}><input id="h-to" type="date" className="input" value={custom.to} onChange={(e) => setCustom({ ...custom, to: e.target.value })} /></Field>
            </>
          )}
        </div>
      </section>
      <ErrorNotice error={summary.error || history.error} onRetry={() => { summary.reload(); history.reload(); }} />
      {summary.loading && !s ? <Spinner /> : s && !s.has_data ? (
        <section className="panel"><Empty title="No readings in this period">There are no simulated readings for {plant?.name} between {fmtDateTime(s.range.from, hour12)} and {fmtDateTime(s.range.to, hour12)}. Run the simulation or choose a wider period.</Empty></section>
      ) : s && (
        <>
          <section className="panel">
            <header><h2>{SENSOR_LABEL[sensor]} over time</h2><SimTag /></header>
            {history.data && <SensorChart parameter={sensor} points={history.data.points} thresholds={status.data?.thresholds} hour12={hour12} />}
            {history.data?.downsampled && <div className="body small muted">{history.data.count} readings were averaged into {history.data.points.length} points for display.</div>}
          </section>

          <section className="panel">
            <header><h2>Summary by sensor</h2><span className="small muted num">{s.reading_count} readings</span></header>
            <div className="table-wrap">
              <table>
                <thead><tr><th>Sensor</th><th>Min</th><th>Average</th><th>Max</th><th>Readings</th><th>Trend over period</th></tr></thead>
                <tbody>
                  {SENSOR_KEYS.map((k) => { const st = s.sensors[k]; const t = trendMeta(st.trend); return (
                    <tr key={k}><td>{st.label}</td><td className="num">{fmtNum(st.min)} {SENSOR_UNIT[k] === '% (normalized)' ? '%' : st.unit}</td><td className="num">{fmtNum(st.avg)}</td><td className="num">{fmtNum(st.max)}</td><td className="num">{st.count}</td>
                      <td><span className="row" style={{ gap: 4 }}><t.Icon size={13} aria-hidden="true" />{t.label}{st.change !== null && st.change !== undefined ? ` (${st.change > 0 ? '+' : ''}${fmtNum(st.change)})` : ''}</span></td></tr>
                  ); })}
                </tbody>
              </table>
            </div>
          </section>

          <div className="grid-2">
            <section className="panel">
              <header><h2>Environmental conditions</h2></header>
              <div className="body stack" style={{ gap: 10 }}>
                {SENSOR_KEYS.map((k) => { const c = s.conditions[k]; return (
                  <div key={k}>
                    <div className="small" style={{ marginBottom: 3 }}>{SENSOR_LABEL[k]}</div>
                    <div className="bar" role="img" aria-label={`${SENSOR_LABEL[k]}: ` + CLASS_ORDER.filter((o) => c[o]).map((o) => `${CLASS_NAME[o]} ${Math.round(100 * c[o] / s.reading_count)}%`).join(', ')}>
                      {CLASS_ORDER.map((o) => c[o] ? <span key={o} style={{ width: `${100 * c[o] / s.reading_count}%`, background: CLASS_COLOR[o], borderRight: '1px solid #fff' }} title={`${CLASS_NAME[o]}: ${c[o]}`} /> : null)}
                    </div>
                    <div className="small muted">{CLASS_ORDER.filter((o) => c[o]).map((o) => `${CLASS_NAME[o]} ${Math.round(100 * c[o] / s.reading_count)}%`).join(' · ')}</div>
                  </div>
                ); })}
                <div className="small muted">Overall health: healthy {s.health.healthy}, needs attention {s.health.needs_attention}, critical {s.health.critical} reading(s).</div>
              </div>
            </section>
            <section className="panel">
              <header><h2>Alerts in period</h2></header>
              <div className="body">
                <div className="row" style={{ gap: 18 }}>
                  <span><strong className="num" style={{ fontSize: 20 }}>{s.alerts.total}</strong> <span className="small muted">raised</span></span>
                  <span><strong className="num" style={{ fontSize: 20 }}>{s.alerts.by_severity.critical}</strong> <span className="small muted">critical</span></span>
                  <span><strong className="num" style={{ fontSize: 20 }}>{s.alerts.by_severity.warning}</strong> <span className="small muted">warning</span></span>
                  <span className="small muted">{s.alerts.active} active · {s.alerts.resolved} resolved</span>
                </div>
                {s.alerts.total === 0 ? <p className="muted" style={{ marginTop: 8 }}>No alerts were raised in this period.</p> : (
                  <table style={{ marginTop: 8 }}>
                    <thead><tr><th>Condition</th><th>Alerts</th></tr></thead>
                    <tbody>{Object.entries(s.alerts.by_type).sort((a, b) => b[1] - a[1]).map(([t, n]) => <tr key={t}><td>{t.replace(/_/g, ' ')}</td><td className="num">{n}</td></tr>)}</tbody>
                  </table>
                )}
                {s.alerts.by_day_utc.length > 1 && <p className="small muted" style={{ marginTop: 6 }}>Frequency by day (UTC): {s.alerts.by_day_utc.map((d) => `${d.date}: ${d.count}`).join(' · ')}</p>}
              </div>
            </section>
          </div>

          <section className="panel">
            <header><h2>Recommendations triggered</h2></header>
            {s.recommendations.length === 0 ? <Empty title="No actions were triggered" /> : (
              <div className="table-wrap"><table>
                <thead><tr><th>Recommendation</th><th>Type</th><th>Readings</th><th>Share</th></tr></thead>
                <tbody>{s.recommendations.map((r) => <tr key={r.rule_id}><td>{r.title}</td><td><Tag tone="muted">{r.category}</Tag></td><td className="num">{r.readings}</td><td className="num">{Math.round(r.share_of_readings * 100)}%</td></tr>)}</tbody>
              </table></div>
            )}
          </section>

          <section className="panel">
            <header>
              <h2>Report</h2>
              <button className="btn small" onClick={() => setShowReport((v) => !v)}><FileText size={13} aria-hidden="true" />{showReport ? 'Hide report' : 'Generate report'}</button>
              {report.data && <button className="btn small" onClick={() => download(`plant-report-${plant?.name.replace(/\W+/g, '-').toLowerCase()}.md`, report.data.markdown)}><Download size={13} aria-hidden="true" />Download (.md)</button>}
            </header>
            {showReport && (report.loading && !report.data ? <Spinner label="Generating report" /> : report.data && (
              <div className="body stack" style={{ gap: 8 }}>
                <div className="small muted">Generated {fmtDateTime(report.data.generated_at, hour12)} · all data is simulated</div>
                {report.data.sections.map((sec) => (
                  <div key={sec.heading}><h3>{sec.heading}</h3><ul style={{ margin: '3px 0 0 18px', padding: 0 }}>{sec.lines.map((l, i) => <li key={i}>{l}</li>)}</ul></div>
                ))}
              </div>
            ))}
          </section>
        </>
      )}
    </div>
  );
}
