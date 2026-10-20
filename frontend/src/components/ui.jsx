import { useEffect, useRef } from 'react';
import { AlertCircle, X, Info } from 'lucide-react';
import { classMeta, healthMeta, severityMeta } from '../util.js';

export function Tag({ tone = 'muted', Icon, children }) {
  return (
    <span className={`tag ${tone}`}>
      {Icon && <Icon size={13} aria-hidden="true" />}
      {children}
    </span>
  );
}
export const ClassTag = ({ code }) => { const m = classMeta(code); return <Tag tone={m.tone} Icon={m.Icon}>{m.label}</Tag>; };
export const HealthTag = ({ status }) => { const m = healthMeta(status); return <Tag tone={m.tone} Icon={m.Icon}>{m.label}</Tag>; };
export const SeverityTag = ({ severity }) => { const m = severityMeta(severity); return <Tag tone={m.tone} Icon={m.Icon}>{m.label}</Tag>; };
export const SimTag = () => <span className="tag sim">Simulated data</span>;

export function Spinner({ label = 'Loading' }) {
  return <div className="loading" role="status"><span className="spinner" aria-hidden="true" />{label}…</div>;
}

export function Empty({ title, children, action }) {
  return (
    <div className="empty">
      <h3>{title}</h3>
      {children && <p>{children}</p>}
      {action}
    </div>
  );
}

export function ErrorNotice({ error, onRetry }) {
  if (!error) return null;
  return (
    <div className="notice error" role="alert">
      <AlertCircle size={16} aria-hidden="true" style={{ flex: 'none', marginTop: 2 }} />
      <div style={{ flex: 1 }}>{error}</div>
      {onRetry && <button className="btn small" onClick={onRetry}>Retry</button>}
    </div>
  );
}

export function Notice({ children, tone }) {
  return (
    <div className={`notice ${tone || ''}`}>
      <Info size={16} aria-hidden="true" style={{ flex: 'none', marginTop: 2 }} />
      <div>{children}</div>
    </div>
  );
}

export function Field({ label, htmlFor, error, hint, children, wide }) {
  return (
    <div className={`field ${wide ? 'wide' : ''}`}>
      <label htmlFor={htmlFor}>{label}</label>
      {children}
      {hint && !error && <span className="hint">{hint}</span>}
      {error && <span className="err" id={`${htmlFor}-err`} role="alert"><AlertCircle size={12} aria-hidden="true" />{error}</span>}
    </div>
  );
}

export function Modal({ title, onClose, children, footer, narrow }) {
  const ref = useRef(null);
  useEffect(() => {
    const prev = document.activeElement;
    ref.current?.focus();
    const onKey = (e) => { if (e.key === 'Escape') onClose(); };
    document.addEventListener('keydown', onKey);
    return () => { document.removeEventListener('keydown', onKey); prev?.focus?.(); };
  }, [onClose]);
  return (
    <div className="overlay" onMouseDown={(e) => { if (e.target === e.currentTarget) onClose(); }}>
      <div className={`dialog ${narrow ? 'narrow' : ''}`} role="dialog" aria-modal="true" aria-label={title} tabIndex={-1} ref={ref}>
        <header>
          <h2>{title}</h2>
          <button className="btn ghost small" onClick={onClose} aria-label="Close dialog"><X size={16} /></button>
        </header>
        <div className="body">{children}</div>
        {footer && <footer>{footer}</footer>}
      </div>
    </div>
  );
}

export function Confirm({ title, message, confirmLabel = 'Delete', busy, onConfirm, onCancel }) {
  return (
    <Modal narrow title={title} onClose={onCancel} footer={
      <>
        <button className="btn" onClick={onCancel} disabled={busy}>Cancel</button>
        <button className="btn danger solid" onClick={onConfirm} disabled={busy}>{busy ? 'Working…' : confirmLabel}</button>
      </>
    }>
      {message}
    </Modal>
  );
}

export function PageHead({ title, subtitle, children }) {
  return (
    <div className="page-head">
      <div>
        <h1>{title}</h1>
        {subtitle && <p className="muted" style={{ margin: 0 }}>{subtitle}</p>}
      </div>
      {children && <div className="actions">{children}</div>}
    </div>
  );
}

export function NoPlant() {
  return (
    <div className="panel">
      <Empty title="No plant selected">Create a plant profile on the My Plants page to start.</Empty>
    </div>
  );
}
