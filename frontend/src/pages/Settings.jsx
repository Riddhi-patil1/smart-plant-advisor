import { useEffect, useState } from 'react';
import { api, ApiError } from '../api.js';
import { useApp } from '../context.jsx';
import { useAction } from '../hooks.js';
import { Field, Notice, PageHead, Spinner } from '../components/ui.jsx';

const GROUPS = [
  ['Simulation', ['sampling_interval_seconds']],
  ['Classification (critical margins beyond each warning threshold)', ['critical_margin_soil_moisture', 'critical_margin_temperature', 'critical_margin_humidity', 'critical_margin_light', 'trend_window']],
  ['Alert behaviour', ['alert_min_severity', 'auto_resolve_alerts']],
  ['Application preferences', ['default_date_range', 'time_format', 'display_name']],
];
const CHOICE_LABEL = { warning: 'Warning and critical', critical: 'Critical only', today: 'Today', '7d': 'Last 7 Days', '30d': 'Last 30 Days', '24h': '24-hour', '12h': '12-hour (AM/PM)' };

export default function Settings() {
  const { settings, loadSettings, loadSim, bump, toast } = useApp();
  const [form, setForm] = useState(null);
  const [errors, setErrors] = useState({});
  const [busy, exec] = useAction();
  useEffect(() => { if (settings && !form) setForm(settings.values); }, [settings, form]);
  if (!settings || !form) return <Spinner />;
  const schema = settings.schema;
  const dirty = JSON.stringify(form) !== JSON.stringify(settings.values);

  const save = (e) => {
    e.preventDefault();
    exec(async () => {
      setErrors({});
      try {
        const payload = {};
        Object.keys(schema).forEach((k) => { payload[k] = ['number', 'int'].includes(schema[k].type) ? Number(form[k]) : form[k]; });
        const r = await api.put('/settings', payload);
        await loadSettings(); await loadSim(); bump();
        setForm(r.values);
        toast('Settings saved and applied.');
      } catch (err) {
        if (err instanceof ApiError && Object.keys(err.fields).length) setErrors(err.fields);
        toast(err.message, 'crit');
      }
    });
  };

  const control = (k) => {
    const s = schema[k];
    const common = { id: `s-${k}`, className: 'input', 'aria-invalid': !!errors[k] };
    if (s.type === 'bool') return <label className="check"><input id={`s-${k}`} type="checkbox" checked={!!form[k]} onChange={(e) => setForm({ ...form, [k]: e.target.checked })} />Enabled</label>;
    if (s.type === 'choice') return <select {...common} value={form[k]} onChange={(e) => setForm({ ...form, [k]: e.target.value })}>{s.choices.map((c) => <option key={c} value={c}>{CHOICE_LABEL[c] || c}</option>)}</select>;
    if (s.type === 'text') return <input {...common} value={form[k]} maxLength={s.max} onChange={(e) => setForm({ ...form, [k]: e.target.value })} />;
    return <input {...common} type="number" step={s.type === 'int' ? 1 : 'any'} min={s.min} max={s.max} value={form[k]} onChange={(e) => setForm({ ...form, [k]: e.target.value })} />;
  };

  return (
    <form className="stack" onSubmit={save} noValidate>
      <PageHead title="Settings" subtitle="Global preferences, stored in SQLite.">
        <button type="button" className="btn" disabled={busy} onClick={() => { setForm(settings.defaults); setErrors({}); }}>Restore defaults</button>
        <button type="submit" className="btn primary" disabled={busy || !dirty}>{busy ? 'Saving…' : 'Save settings'}</button>
      </PageHead>
      <Notice>Plant-specific preferred ranges and warning thresholds belong to each plant profile (My Plants) and are never overwritten here. Critical margins below only decide how far beyond a plant's warning threshold a reading must be to count as Critical.</Notice>
      {GROUPS.map(([title, keys]) => (
        <fieldset key={title} className="panel" style={{ padding: 14 }}>
          <legend>{title}</legend>
          <div className="form-grid">
            {keys.map((k) => (
              <Field key={k} label={schema[k].label} htmlFor={`s-${k}`} error={errors[k]}
                hint={schema[k].min !== undefined ? `Allowed: ${schema[k].min}–${schema[k].max}` : undefined}>{control(k)}</Field>
            ))}
          </div>
        </fieldset>
      ))}
      <p className="small muted">The profile name is a local label for this demo. There is no authentication and no secured account.</p>
    </form>
  );
}
