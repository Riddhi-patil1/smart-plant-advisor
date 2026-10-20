import { useEffect, useState } from 'react';
import { useLocation } from 'react-router-dom';
import { CheckCircle2, ImageOff, Pencil, Plus, Trash2 } from 'lucide-react';
import { api, ApiError } from '../api.js';
import { useApp } from '../context.jsx';
import { useAction } from '../hooks.js';
import { Confirm, Empty, Field, Modal, Notice, PageHead, Tag } from '../components/ui.jsx';
import { fmtDateTime } from '../util.js';

const BLANK = {
  name: '', species: '', image_url: '', planting_date: '', description: '',
  moisture_min: '40', moisture_max: '60', moisture_warning: '35',
  temperature_min: '18', temperature_max: '30', temperature_warning: '32',
  humidity_min: '40', humidity_max: '70', light_min: '40', light_max: '70',
  watering_guidance: '', care_notes: '',
};
const NUM = ['moisture_min', 'moisture_max', 'moisture_warning', 'temperature_min', 'temperature_max', 'temperature_warning', 'humidity_min', 'humidity_max', 'light_min', 'light_max'];

function validate(f) {
  const e = {};
  if (!f.name.trim()) e.name = 'Name is required.';
  NUM.forEach((k) => { if (f[k] === '' || Number.isNaN(Number(f[k]))) e[k] = 'Enter a number.'; });
  const n = (k) => Number(f[k]);
  const pair = (a, b, lo, hi, label) => {
    if (!e[a] && (n(a) < lo || n(a) > hi)) e[a] = `${label} minimum must be ${lo}–${hi}.`;
    if (!e[b] && (n(b) < lo || n(b) > hi)) e[b] = `${label} maximum must be ${lo}–${hi}.`;
    if (!e[a] && !e[b] && n(a) >= n(b)) e[b] = 'Maximum must be greater than the minimum.';
  };
  pair('moisture_min', 'moisture_max', 0, 100, 'Soil moisture');
  pair('temperature_min', 'temperature_max', -10, 60, 'Temperature');
  pair('humidity_min', 'humidity_max', 0, 100, 'Humidity');
  pair('light_min', 'light_max', 0, 100, 'Light');
  if (!e.moisture_warning && !e.moisture_min && n('moisture_warning') > n('moisture_min')) e.moisture_warning = 'Must not exceed the preferred minimum.';
  if (!e.moisture_warning && n('moisture_warning') < 0) e.moisture_warning = 'Must be 0 or more.';
  if (!e.temperature_warning && !e.temperature_max && n('temperature_warning') < n('temperature_max')) e.temperature_warning = 'Must not be below the preferred maximum.';
  if (f.image_url && !/^https?:\/\/\S+$/i.test(f.image_url)) e.image_url = 'Must start with http:// or https://.';
  return e;
}

function PlantForm({ plant, onClose, onSaved }) {
  const { toast } = useApp();
  const [form, setForm] = useState(() => {
    if (!plant) return BLANK;
    const f = {};
    Object.keys(BLANK).forEach((k) => { f[k] = plant[k] === null || plant[k] === undefined ? '' : String(plant[k]); });
    return f;
  });
  const [errors, setErrors] = useState({});
  const [busy, exec] = useAction();
  const set = (k) => (e) => setForm((f) => ({ ...f, [k]: e.target.value }));
  const id = (k) => `pf-${k}`;
  const input = (k, props = {}) => (
    <input id={id(k)} className="input" value={form[k]} onChange={set(k)} aria-invalid={!!errors[k]} aria-describedby={errors[k] ? `${id(k)}-err` : undefined} {...props} />
  );
  const num = (k, label, hint) => (
    <Field label={label} htmlFor={id(k)} error={errors[k]} hint={hint}>{input(k, { type: 'number', step: 'any', inputMode: 'decimal' })}</Field>
  );

  const submit = (e) => {
    e.preventDefault();
    const local = validate(form);
    setErrors(local);
    if (Object.keys(local).length) { toast('Please fix the highlighted fields.', 'warn'); return; }
    const body = { ...form };
    NUM.forEach((k) => { body[k] = Number(form[k]); });
    exec(async () => {
      try {
        const saved = plant ? await api.put(`/plants/${plant.id}`, body) : await api.post('/plants', body);
        toast(plant ? 'Plant updated. Recommendations and alerts were recalculated.' : 'Plant created.');
        onSaved(saved);
      } catch (err) {
        if (err instanceof ApiError && Object.keys(err.fields).length) setErrors(err.fields);
        toast(err.message, 'crit');
      }
    });
  };

  return (
    <Modal title={plant ? `Edit ${plant.name}` : 'New plant profile'} onClose={onClose} footer={
      <>
        <button className="btn" type="button" onClick={onClose} disabled={busy}>Cancel</button>
        <button className="btn primary" form="plant-form" type="submit" disabled={busy}>{busy ? 'Saving…' : plant ? 'Save changes' : 'Create plant'}</button>
      </>
    }>
      <form id="plant-form" onSubmit={submit} noValidate className="stack">
        <Notice>Thresholds are editable starting points, not universal biological facts. Adjust them to your plant and conditions.</Notice>
        <div className="form-grid">
          <Field label="Plant name *" htmlFor={id('name')} error={errors.name}>{input('name', { maxLength: 80, required: true, autoFocus: true })}</Field>
          <Field label="Species" htmlFor={id('species')} error={errors.species}>{input('species', { maxLength: 120 })}</Field>
          <Field label="Image URL (optional)" htmlFor={id('image_url')} error={errors.image_url}>{input('image_url', { type: 'url', placeholder: 'https://…' })}</Field>
          <Field label="Planting date" htmlFor={id('planting_date')} error={errors.planting_date}>{input('planting_date', { type: 'date', max: new Date().toISOString().slice(0, 10) })}</Field>
          <Field wide label="Description" htmlFor={id('description')} error={errors.description}>
            <textarea id={id('description')} className="input" rows={2} value={form.description} onChange={set('description')} maxLength={1000} />
          </Field>
        </div>
        <fieldset><legend>Soil moisture (%)</legend>
          <div className="form-grid">
            {num('moisture_min', 'Preferred minimum')}{num('moisture_max', 'Preferred maximum')}
            {num('moisture_warning', 'Warning threshold', 'Low-moisture warning at or below this value')}
          </div></fieldset>
        <fieldset><legend>Temperature (°C)</legend>
          <div className="form-grid">
            {num('temperature_min', 'Preferred minimum')}{num('temperature_max', 'Preferred maximum')}
            {num('temperature_warning', 'Warning threshold', 'High-temperature warning above this value')}
          </div></fieldset>
        <fieldset><legend>Relative humidity (%)</legend>
          <div className="form-grid">{num('humidity_min', 'Preferred minimum')}{num('humidity_max', 'Preferred maximum')}</div></fieldset>
        <fieldset><legend>Light (normalized level, 0–100)</legend>
          <div className="form-grid">{num('light_min', 'Preferred minimum')}{num('light_max', 'Preferred maximum')}</div></fieldset>
        <div className="form-grid">
          <Field wide label="Watering guidance" htmlFor={id('watering_guidance')} error={errors.watering_guidance}>
            <textarea id={id('watering_guidance')} className="input" rows={2} value={form.watering_guidance} onChange={set('watering_guidance')} maxLength={1000} />
          </Field>
          <Field wide label="Additional care notes" htmlFor={id('care_notes')} error={errors.care_notes}>
            <textarea id={id('care_notes')} className="input" rows={2} value={form.care_notes} onChange={set('care_notes')} maxLength={1000} />
          </Field>
        </div>
      </form>
    </Modal>
  );
}

export default function Plants() {
  const { plants, activeId, selectPlant, loadPlants, refreshAll, bump, toast } = useApp();
  const location = useLocation();
  const [editing, setEditing] = useState(null); // null | 'new' | plant
  const [deleting, setDeleting] = useState(null);
  const [busy, exec] = useAction();

  useEffect(() => {
    const id = location.state?.edit;
    if (id) { const p = plants.find((x) => x.id === id); if (p) setEditing(p); window.history.replaceState({}, ''); }
  }, [location.state, plants]);

  const confirmDelete = () => exec(async () => {
    try {
      const r = await api.del(`/plants/${deleting.id}`);
      toast(`Deleted ${deleting.name} with ${r.readings_removed} reading(s) and ${r.alerts_removed} alert(s).`);
      setDeleting(null);
      await refreshAll();
      bump();
    } catch (e) { toast(e.message, 'crit'); }
  });

  return (
    <div className="stack">
      <PageHead title="My Plants" subtitle="Plant profiles and their preferred ranges. Each plant keeps its own readings, alerts and thresholds.">
        <button className="btn primary" onClick={() => setEditing('new')}><Plus size={14} aria-hidden="true" />New plant</button>
      </PageHead>
      <section className="panel">
        {plants.length === 0 ? (
          <Empty title="No plant profiles yet" action={<button className="btn primary" onClick={() => setEditing('new')}>Create your first plant</button>}>
            Add a profile to start a simulation and receive advice.
          </Empty>
        ) : (
          <div className="table-wrap">
            <table>
              <thead><tr><th>Plant</th><th>Moisture %</th><th>Temp °C</th><th>Humidity %</th><th>Light (norm.)</th><th>Readings</th><th>Alerts</th><th>Updated</th><th><span className="sr-only">Actions</span></th></tr></thead>
              <tbody>
                {plants.map((p) => (
                  <tr key={p.id}>
                    <td>
                      <div className="row" style={{ gap: 10, flexWrap: 'nowrap' }}>
                        {p.image_url ? <img src={p.image_url} alt="" style={{ width: 34, height: 34, objectFit: 'cover', borderRadius: 4 }} onError={(e) => { e.currentTarget.style.display = 'none'; }} /> : <span className="plant-img" style={{ width: 34, height: 34 }} aria-hidden="true"><ImageOff size={14} /></span>}
                        <div><strong>{p.name}</strong> {p.id === activeId && <Tag tone="ok" Icon={CheckCircle2}>Active</Tag>}<div className="small muted"><em>{p.species || '—'}</em></div></div>
                      </div>
                    </td>
                    <td className="num">{p.moisture_min}–{p.moisture_max} <span className="small muted">(warn {p.moisture_warning})</span></td>
                    <td className="num">{p.temperature_min}–{p.temperature_max} <span className="small muted">(warn {p.temperature_warning})</span></td>
                    <td className="num">{p.humidity_min}–{p.humidity_max}</td>
                    <td className="num">{p.light_min}–{p.light_max}</td>
                    <td className="num">{p.reading_count}</td>
                    <td className="num">{p.active_alert_count} active</td>
                    <td className="small muted num">{fmtDateTime(p.updated_at)}</td>
                    <td>
                      <div className="row" style={{ gap: 4, flexWrap: 'nowrap' }}>
                        {p.id !== activeId && <button className="btn small" onClick={async () => { try { await selectPlant(p.id); toast(`${p.name} is now the active plant.`); } catch (e) { toast(e.message, 'crit'); } }}>Select</button>}
                        <button className="btn small" onClick={() => setEditing(p)} aria-label={`Edit ${p.name}`}><Pencil size={13} aria-hidden="true" />Edit</button>
                        <button className="btn small danger" onClick={() => setDeleting(p)} aria-label={`Delete ${p.name}`}><Trash2 size={13} aria-hidden="true" /></button>
                      </div>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </section>
      {plants.some((p) => p.watering_guidance || p.care_notes) && (
        <section className="panel">
          <header><h2>Care guidance</h2></header>
          <ul className="list">
            {plants.map((p) => (
              <li key={p.id}><strong>{p.name}</strong>
                {p.watering_guidance && <div><span className="muted">Watering:</span> {p.watering_guidance}</div>}
                {p.care_notes && <div><span className="muted">Notes:</span> {p.care_notes}</div>}
              </li>
            ))}
          </ul>
        </section>
      )}
      {editing && (
        <PlantForm plant={editing === 'new' ? null : editing} onClose={() => setEditing(null)}
          onSaved={async () => { setEditing(null); await loadPlants(); bump(); }} />
      )}
      {deleting && (
        <Confirm title={`Delete ${deleting.name}?`} busy={busy} onCancel={() => setDeleting(null)} onConfirm={confirmDelete}
          message={<><p>This permanently deletes the profile together with its <strong>{deleting.reading_count} stored reading(s)</strong> and all of its alerts. This cannot be undone.</p><p className="muted small">Other plants are not affected.</p></>} />
      )}
    </div>
  );
}
