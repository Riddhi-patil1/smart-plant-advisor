import { useEffect, useState } from 'react';
import { NavLink, Navigate, Route, Routes, useLocation, Link } from 'react-router-dom';
import { Bell, Clock, Info, LayoutDashboard, LineChart, Leaf, Menu, Settings as Cog, Sprout, SlidersHorizontal, Lightbulb, UserRound, X } from 'lucide-react';
import { useApp } from './context.jsx';
import { ErrorNotice, Spinner } from './components/ui.jsx';
import Dashboard from './pages/Dashboard.jsx';
import Plants from './pages/Plants.jsx';
import Advisory from './pages/Advisory.jsx';
import Simulation from './pages/Simulation.jsx';
import History from './pages/History.jsx';
import Alerts from './pages/Alerts.jsx';
import Settings from './pages/Settings.jsx';
import About from './pages/About.jsx';

const NAV = [
  { to: '/', label: 'Dashboard', Icon: LayoutDashboard, title: 'Dashboard' },
  { to: '/plants', label: 'My Plants', Icon: Sprout, title: 'My Plants' },
  { to: '/advisory', label: 'Smart Advisory', Icon: Lightbulb, title: 'Smart Advisory' },
  { to: '/simulation', label: 'Sensor Simulation', Icon: SlidersHorizontal, title: 'Sensor Simulation' },
  { to: '/history', label: 'History & Analytics', Icon: LineChart, title: 'History & Analytics' },
  { to: '/alerts', label: 'Alerts', Icon: Bell, title: 'Alerts' },
  { to: '/settings', label: 'Settings', Icon: Cog, title: 'Settings' },
  { to: '/about', label: 'About Project', Icon: Info, title: 'About Project' },
];

function Clock12() {
  const { hour12 } = useApp();
  const [now, setNow] = useState(new Date());
  useEffect(() => { const id = setInterval(() => setNow(new Date()), 1000); return () => clearInterval(id); }, []);
  return (
    <span className="group small num hide-sm" title="Local date and time">
      <Clock size={14} aria-hidden="true" />
      {now.toLocaleString(undefined, { weekday: 'short', day: '2-digit', month: 'short', hour: '2-digit', minute: '2-digit', hour12 })}
    </span>
  );
}

export default function App() {
  const { plants, activeId, selectPlant, sim, alertCounts, backendError, loaded, refreshAll, settings, toasts, setToasts, toast } = useApp();
  const [open, setOpen] = useState(false);
  const location = useLocation();
  useEffect(() => setOpen(false), [location.pathname]);
  const current = NAV.find((n) => (n.to === '/' ? location.pathname === '/' : location.pathname.startsWith(n.to))) || NAV[0];
  const state = sim?.state || 'stopped';
  const unread = alertCounts.unread;

  return (
    <div className="shell">
      <aside className={`sidebar ${open ? 'open' : ''}`} aria-label="Primary">
        <div className="brand"><Leaf size={20} aria-hidden="true" /><span>Smart Plant<br />Advisor</span></div>
        <nav className="nav">
          {NAV.map(({ to, label, Icon }) => (
            <NavLink key={to} to={to} end={to === '/'} className={({ isActive }) => (isActive ? 'active' : '')}>
              <Icon size={16} aria-hidden="true" />{label}
              {to === '/alerts' && unread > 0 && <span className="badge" aria-label={`${unread} unread alerts`}>{unread}</span>}
            </NavLink>
          ))}
        </nav>
        <div style={{ marginTop: 'auto', fontSize: 11, opacity: .75, padding: '0 8px' }}>Prototype · simulated sensors only</div>
      </aside>
      <div className={`scrim ${open ? 'open' : ''}`} onClick={() => setOpen(false)} aria-hidden="true" />

      <header className="topbar">
        <button className="btn menu-btn small" onClick={() => setOpen((o) => !o)} aria-label={open ? 'Close menu' : 'Open menu'} aria-expanded={open}>
          {open ? <X size={16} /> : <Menu size={16} />}
        </button>
        <div className="title">
          <span className="app">Smart Plant Monitoring &amp; Advisory</span>
          <strong>{current.title}</strong>
        </div>
        <label className="group small" htmlFor="plant-select">
          <span className="hide-sm muted">Plant</span>
          <select id="plant-select" className="input" style={{ width: 'auto', maxWidth: 170 }} value={activeId ?? ''} disabled={!plants.length}
            onChange={async (e) => { try { await selectPlant(e.target.value); } catch (err) { toast(err.message, 'crit'); } }}>
            {!plants.length && <option value="">No plants</option>}
            {plants.map((p) => <option key={p.id} value={p.id}>{p.name}</option>)}
          </select>
        </label>
        <Link to="/simulation" className="state-chip" title="Simulation state (managed by the backend)">
          <span className={`dot ${state}`} aria-hidden="true" />Simulation: {state}
        </Link>
        <Link to="/alerts" className="btn small" aria-label={`Notifications: ${unread} unread alerts`}>
          <Bell size={15} aria-hidden="true" />{unread > 0 ? <span className="badge">{unread}</span> : <span className="small muted">0</span>}
        </Link>
        <Clock12 />
        <Link to="/settings" className="group small" title="Local demo profile (not a secured account)" style={{ textDecoration: 'none', color: 'inherit' }}>
          <UserRound size={15} aria-hidden="true" />
          <span className="hide-sm">{settings?.values?.display_name || 'Demo user'} <span className="muted">(local demo)</span></span>
        </Link>
      </header>

      <main className="main" id="main">
        {backendError && <div style={{ marginBottom: 12 }}><ErrorNotice error={backendError} onRetry={refreshAll} /></div>}
        {!loaded ? <Spinner label="Connecting to the backend" /> : (
          <Routes>
            <Route path="/" element={<Dashboard />} />
            <Route path="/plants" element={<Plants />} />
            <Route path="/advisory" element={<Advisory />} />
            <Route path="/simulation" element={<Simulation />} />
            <Route path="/history" element={<History />} />
            <Route path="/alerts" element={<Alerts />} />
            <Route path="/settings" element={<Settings />} />
            <Route path="/about" element={<About />} />
            <Route path="*" element={<Navigate to="/" replace />} />
          </Routes>
        )}
      </main>

      <footer className="footer">Software prototype using simulated sensor data. Physical sensor integration is planned for future development.</footer>

      <div className="toasts" aria-live="polite">
        {toasts.map((t) => (
          <div key={t.id} className={`toast ${t.tone === 'ok' ? '' : t.tone}`} role={t.tone === 'crit' ? 'alert' : 'status'}>
            <span style={{ flex: 1 }}>{t.message}</span>
            <button className="btn ghost small" aria-label="Dismiss" onClick={() => setToasts((x) => x.filter((y) => y.id !== t.id))}><X size={14} /></button>
          </div>
        ))}
      </div>
    </div>
  );
}
