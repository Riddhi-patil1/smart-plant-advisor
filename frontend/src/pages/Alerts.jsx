import { useState } from 'react';
import { CheckCheck, Eye } from 'lucide-react';
import { api, qs } from '../api.js';
import { useApp } from '../context.jsx';
import { useAction, useLoad } from '../hooks.js';
import { Empty, ErrorNotice, Field, Modal, PageHead, SeverityTag, SimTag, Spinner, Tag } from '../components/ui.jsx';
import { SENSOR_LABEL, SHORT_UNIT, fmtDateTime } from '../util.js';

export default function Alerts() {
  const { plants, activeId, loadAlertCounts, bump, dataVersion, toast, hour12 } = useApp();
  const [f, setF] = useState({ plant_id: '', severity: '', status: '', from: '', to: '' });
  const [detail, setDetail] = useState(null);
  const [busy, exec] = useAction();
  const set = (k) => (e) => setF((x) => ({ ...x, [k]: e.target.value }));
  const dateBad = f.from && f.to && f.from > f.to;

  const q = useLoad(() => (dateBad ? Promise.resolve(null) : api.get(`/alerts${qs(f)}`)), [f.plant_id, f.severity, f.status, f.from, f.to, dataVersion]);
  const items = q.data?.alerts || [];

  const after = async () => { await loadAlertCounts(); q.reload(); };
  const markRead = (a, read = true) => exec(async () => {
    try { const u = await api.post(`/alerts/${a.id}/${read ? 'read' : 'unread'}`); if (detail?.id === a.id) setDetail({ ...detail, ...u }); await after(); } catch (e) { toast(e.message, 'crit'); }
  });
  const readAll = () => exec(async () => {
    try { const r = await api.post(`/alerts/read-all${qs({ plant_id: f.plant_id })}`); toast(`${r.updated} alert(s) marked as read.`); await after(); } catch (e) { toast(e.message, 'crit'); }
  });
  const open = async (a) => { setDetail(a); if (!a.is_read) markRead(a, true); };

  return (
    <div className="stack">
      <PageHead title="Alerts" subtitle="Generated from simulated readings. Alerts resolve themselves when the condition recovers.">
        <button className="btn" onClick={readAll} disabled={busy || !(q.data?.counts?.unread)}><CheckCheck size={14} aria-hidden="true" />Mark all as read</button>
      </PageHead>
      <section className="panel">
        <div className="body form-grid" role="search" aria-label="Alert filters">
          <Field label="Plant" htmlFor="af-plant"><select id="af-plant" className="input" value={f.plant_id} onChange={set('plant_id')}><option value="">All plants</option>{plants.map((p) => <option key={p.id} value={p.id}>{p.name}</option>)}</select></Field>
          <Field label="Severity" htmlFor="af-sev"><select id="af-sev" className="input" value={f.severity} onChange={set('severity')}><option value="">All</option><option value="warning">Warning</option><option value="critical">Critical</option></select></Field>
          <Field label="Status" htmlFor="af-status"><select id="af-status" className="input" value={f.status} onChange={set('status')}><option value="">All</option><option value="active">Active</option><option value="resolved">Resolved</option></select></Field>
          <Field label="From" htmlFor="af-from"><input id="af-from" type="date" className="input" value={f.from} onChange={set('from')} /></Field>
          <Field label="To" htmlFor="af-to" error={dateBad ? 'End date must not be before the start date.' : null}><input id="af-to" type="date" className="input" value={f.to} onChange={set('to')} aria-invalid={dateBad} /></Field>
          <div className="field" style={{ justifyContent: 'flex-end' }}><button className="btn" onClick={() => setF({ plant_id: '', severity: '', status: '', from: '', to: '' })}>Clear filters</button></div>
        </div>
      </section>
      <ErrorNotice error={q.error} onRetry={q.reload} />
      <section className="panel">
        {q.loading && !q.data ? <Spinner /> : items.length === 0 ? (
          <Empty title="No alerts match">Alerts appear when a simulated reading crosses a plant's thresholds.</Empty>
        ) : (
          <div className="table-wrap">
            <table>
              <thead><tr><th>Severity</th><th>Alert</th><th>Plant</th><th>Value / threshold</th><th>Status</th><th>Created</th><th>Updated</th><th>Read</th><th><span className="sr-only">Actions</span></th></tr></thead>
              <tbody>
                {items.map((a) => (
                  <tr key={a.id} className={`clickable ${a.is_read ? '' : 'unread'}`} onClick={() => open(a)}>
                    <td><SeverityTag severity={a.severity} /></td>
                    <td><strong>{a.title}</strong><div className="small muted" style={{ maxWidth: 360 }}>{a.description}</div></td>
                    <td>{a.plant_name}</td>
                    <td className="num">{a.sensor_value}{SHORT_UNIT[a.parameter]} / {a.direction === 'low' ? '<' : '>'} {a.threshold_value}{SHORT_UNIT[a.parameter]}<div className="small muted">{a.threshold_kind} threshold · seen {a.occurrence_count}×</div></td>
                    <td><Tag tone={a.status === 'active' ? 'warn' : 'ok'}>{a.status === 'active' ? 'Active' : 'Resolved'}</Tag></td>
                    <td className="small num">{fmtDateTime(a.created_at, hour12)}</td>
                    <td className="small num">{fmtDateTime(a.updated_at, hour12)}</td>
                    <td>{a.is_read ? 'Read' : <strong style={{ color: 'var(--green)' }}>Unread</strong>}</td>
                    <td onClick={(e) => e.stopPropagation()}>
                      <div className="row" style={{ gap: 4, flexWrap: 'nowrap' }}>
                        <button className="btn small" onClick={() => open(a)} aria-label={`Details for ${a.title}`}><Eye size={13} aria-hidden="true" />Details</button>
                        {!a.is_read && <button className="btn small" disabled={busy} onClick={() => markRead(a)}>Mark read</button>}
                      </div>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </section>
      {detail && (
        <Modal title={detail.title} onClose={() => setDetail(null)} footer={<button className="btn" onClick={() => setDetail(null)}>Close</button>}>
          <div className="stack" style={{ gap: 10 }}>
            <div className="row"><SeverityTag severity={detail.severity} /><Tag tone={detail.status === 'active' ? 'warn' : 'ok'}>{detail.status === 'active' ? 'Active' : `Resolved ${fmtDateTime(detail.resolved_at, hour12)}`}</Tag><SimTag /></div>
            <p style={{ margin: 0 }}>{detail.description}</p>
            <dl className="kv">
              <dt>Plant</dt><dd>{detail.plant_name}</dd>
              <dt>Parameter</dt><dd>{SENSOR_LABEL[detail.parameter]}</dd>
              <dt>Latest value</dt><dd className="num">{detail.sensor_value} {SHORT_UNIT[detail.parameter]} (simulated)</dd>
              <dt>Threshold</dt><dd className="num">{detail.direction === 'low' ? 'below' : 'above'} {detail.threshold_value} {SHORT_UNIT[detail.parameter]} ({detail.threshold_kind})</dd>
              <dt>Created</dt><dd className="num">{fmtDateTime(detail.created_at, hour12)}</dd>
              <dt>Last updated</dt><dd className="num">{fmtDateTime(detail.updated_at, hour12)} · seen in {detail.occurrence_count} reading(s)</dd>
            </dl>
            <div><h3>Why this alert exists</h3><div className="rec" style={{ padding: 0, border: 0 }}><div className="why">{detail.explanation}</div></div></div>
            <div><h3>Suggested action</h3><p style={{ margin: 0 }}>{detail.recommended_action}</p></div>
            <div className="row">
              {detail.is_read ? <button className="btn small" disabled={busy} onClick={() => markRead(detail, false)}>Mark as unread</button> : <button className="btn small" disabled={busy} onClick={() => markRead(detail, true)}>Mark as read</button>}
              {detail.status === 'active' && <button className="btn small" disabled={busy} onClick={() => exec(async () => { try { const u = await api.post(`/alerts/${detail.id}/resolve`); setDetail({ ...detail, ...u }); await after(); toast('Alert resolved manually. It will reopen if the condition returns.'); } catch (e) { toast(e.message, 'crit'); } })}>Resolve manually</button>}
            </div>
          </div>
        </Modal>
      )}
    </div>
  );
}
