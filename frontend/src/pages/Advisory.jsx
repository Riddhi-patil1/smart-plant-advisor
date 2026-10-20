import { Droplets, Thermometer } from 'lucide-react';
import { Link } from 'react-router-dom';
import { api } from '../api.js';
import { useApp } from '../context.jsx';
import { useLoad } from '../hooks.js';
import { ClassTag, Empty, ErrorNotice, HealthTag, Notice, NoPlant, PageHead, SeverityTag, SimTag, Spinner, Tag } from '../components/ui.jsx';
import { SENSOR_KEYS, SENSOR_LABEL, SHORT_UNIT, fmtDateTime, fmtNum } from '../util.js';

function Rec({ r }) {
  const v = r.values;
  const tone = r.severity === 'critical' ? 'crit' : r.severity === 'warning' ? 'warn' : 'ok';
  return (
    <div className="rec">
      <div className="row" style={{ gap: 8 }}>
        {r.severity === 'info' ? <Tag tone="ok">No action needed</Tag> : <SeverityTag severity={r.severity} />}
        <strong>{r.title}</strong>
      </div>
      <div>{r.message}</div>
      <div className="why" title="The rule that produced this recommendation">{r.explanation}</div>
      <div className="small muted">
        Simulated value <strong className="num">{fmtNum(v.value)} {SHORT_UNIT[r.parameter]}</strong> · preferred {fmtNum(v.preferred_min)}–{fmtNum(v.preferred_max)} · warning threshold {fmtNum(v.warning_threshold)} · critical threshold {fmtNum(v.critical_threshold)}
      </div>
      <ul>{r.actions.map((a, i) => <li key={i}>{a}</li>)}</ul>
      <span hidden>{tone}</span>
    </div>
  );
}

export default function Advisory() {
  const { activeId, activePlant, dataVersion, hour12 } = useApp();
  const q = useLoad(() => (activeId ? api.get(`/plants/${activeId}/recommendations`) : Promise.resolve(null)), [activeId, dataVersion]);
  if (!activeId) return (<><PageHead title="Smart Advisory" /><NoPlant /></>);
  const d = q.data;
  const watering = d?.recommendations.filter((r) => r.category === 'watering') || [];
  const env = d?.recommendations.filter((r) => r.category === 'environment') || [];

  return (
    <div className="stack">
      <PageHead title="Smart Advisory" subtitle={`Rule-based, explainable recommendations for ${activePlant?.name || 'the selected plant'}.`} />
      <Notice>Advisory only. Suggestions come from transparent rules applied to <strong>simulated</strong> readings and your editable plant thresholds. They are not a guaranteed plant-health diagnosis, and watering advice is based on soil moisture, never on a timer.</Notice>
      <ErrorNotice error={q.error} onRetry={q.reload} />
      {q.loading && !d ? <Spinner /> : d && !d.has_data ? (
        <section className="panel"><Empty title="No readings yet" action={<Link to="/simulation" className="btn primary">Open Sensor Simulation</Link>}>Recommendations appear once at least one simulated reading exists for this plant.</Empty></section>
      ) : d && (
        <>
          <section className="panel">
            <header><h2>Overall condition</h2><HealthTag status={d.health.status} /><SimTag /></header>
            <div className="body">
              <p>{d.health.summary}</p>
              <div className="small muted">Based on the reading from {fmtDateTime(d.latest_reading.recorded_at, hour12)}. Recalculated whenever a new reading arrives or the plant thresholds change.</div>
              {d.health.factors.length > 0 && (
                <ul style={{ margin: '8px 0 0 18px', padding: 0 }}>{d.health.factors.map((f, i) => <li key={i}>{f.message}</li>)}</ul>
              )}
            </div>
          </section>
          <div className="grid-2">
            <section className="panel">
              <header><Droplets size={16} aria-hidden="true" /><h2>Watering advice</h2></header>
              {watering.length ? watering.map((r) => <Rec key={r.rule_id} r={r} />) : <Empty title="Nothing to report" />}
            </section>
            <section className="panel">
              <header><Thermometer size={16} aria-hidden="true" /><h2>Environmental advice</h2></header>
              {env.length ? env.map((r) => <Rec key={r.rule_id} r={r} />) : <Empty title="Environment within thresholds">Temperature, humidity and light are all inside the configured thresholds.</Empty>}
            </section>
          </div>
          <section className="panel">
            <header><h2>Thresholds used for this analysis</h2><Link to="/plants" className="small">Edit in My Plants</Link></header>
            <div className="table-wrap">
              <table>
                <thead><tr><th>Parameter</th><th>Reading</th><th>Class</th><th>Critical low</th><th>Warning low</th><th>Preferred</th><th>Warning high</th><th>Critical high</th></tr></thead>
                <tbody>
                  {SENSOR_KEYS.map((k) => {
                    const t = d.thresholds[k];
                    const c = d.latest_reading.classes[k];
                    const u = SHORT_UNIT[k];
                    return (
                      <tr key={k}>
                        <td>{SENSOR_LABEL[k]}</td><td className="num"><strong>{fmtNum(d.latest_reading[k])} {u}</strong></td><td><ClassTag code={c} /></td>
                        <td className="num">&lt; {fmtNum(t.crit_low)}</td><td className="num">&lt; {fmtNum(t.warn_low)}</td>
                        <td className="num">{fmtNum(t.pref_min)}–{fmtNum(t.pref_max)}</td>
                        <td className="num">&gt; {fmtNum(t.warn_high)}</td><td className="num">&gt; {fmtNum(t.crit_high)}</td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>
            <div className="body small muted">Critical thresholds are the warning threshold plus the margins configured under Settings.</div>
          </section>
        </>
      )}
    </div>
  );
}
