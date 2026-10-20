import { CheckCircle2, AlertTriangle, OctagonAlert, ArrowUp, ArrowDown, Minus, CircleHelp } from 'lucide-react';

export const SENSOR_KEYS = ['soil_moisture', 'temperature', 'humidity', 'light'];
export const SENSOR_LABEL = {
  soil_moisture: 'Soil Moisture',
  temperature: 'Temperature',
  humidity: 'Relative Humidity',
  light: 'Light Intensity',
};
export const SENSOR_UNIT = { soil_moisture: '%', temperature: '°C', humidity: '%', light: '% (normalized)' };
export const SHORT_UNIT = { soil_moisture: '%', temperature: '°C', humidity: '%', light: '%' };
export const SENSOR_COLOR = { soil_moisture: '#1f6f50', temperature: '#b4572b', humidity: '#2d6a8f', light: '#9a7b1a' };

export const SCENARIO_LABEL = {
  normal: 'Normal Conditions', dry_soil: 'Dry Soil', high_temperature: 'High Temperature',
  low_humidity: 'Low Humidity', low_light: 'Low Light', multiple: 'Multiple Environmental Problems',
  custom: 'Custom Conditions',
};
export const PROBLEM_LABEL = {
  dry_soil: 'Dry soil', high_temperature: 'High temperature', low_humidity: 'Low humidity', low_light: 'Low light',
};

// Classification code -> label, tone and icon (status is never conveyed by colour alone).
export function classMeta(code) {
  switch (code) {
    case 'normal': return { label: 'Normal', tone: 'ok', Icon: CheckCircle2 };
    case 'low': return { label: 'Low', tone: 'warn', Icon: AlertTriangle };
    case 'high': return { label: 'High', tone: 'warn', Icon: AlertTriangle };
    case 'critical_low': case 'critical_high': return { label: 'Critical', tone: 'crit', Icon: OctagonAlert };
    default: return { label: 'No data', tone: 'muted', Icon: CircleHelp };
  }
}

export function healthMeta(status) {
  switch (status) {
    case 'healthy': return { label: 'Healthy', tone: 'ok', Icon: CheckCircle2 };
    case 'needs_attention': return { label: 'Needs Attention', tone: 'warn', Icon: AlertTriangle };
    case 'critical': return { label: 'Critical', tone: 'crit', Icon: OctagonAlert };
    default: return { label: 'No data', tone: 'muted', Icon: CircleHelp };
  }
}

export function severityMeta(sev) {
  return sev === 'critical'
    ? { label: 'Critical', tone: 'crit', Icon: OctagonAlert }
    : { label: 'Warning', tone: 'warn', Icon: AlertTriangle };
}

export function trendMeta(dir) {
  if (dir === 'rising') return { label: 'Rising', Icon: ArrowUp };
  if (dir === 'falling') return { label: 'Falling', Icon: ArrowDown };
  if (dir === 'stable') return { label: 'Stable', Icon: Minus };
  return { label: 'Not enough data', Icon: Minus };
}

export const fmtNum = (v, d = 1) => (v === null || v === undefined ? '–' : Number(v).toFixed(d).replace(/\.0+$/, ''));

export function fmtDateTime(iso, hour12 = false) {
  if (!iso) return '–';
  return new Date(iso).toLocaleString(undefined, {
    year: 'numeric', month: 'short', day: '2-digit', hour: '2-digit', minute: '2-digit', second: '2-digit', hour12,
  });
}
export function fmtShort(iso, hour12 = false) {
  if (!iso) return '';
  return new Date(iso).toLocaleString(undefined, { month: 'short', day: '2-digit', hour: '2-digit', minute: '2-digit', hour12 });
}
export const fmtTimeOnly = (iso, hour12 = false) =>
  new Date(iso).toLocaleTimeString(undefined, { hour: '2-digit', minute: '2-digit', hour12 });

export function timeAgo(iso) {
  if (!iso) return 'never';
  const s = Math.max(0, Math.round((Date.now() - new Date(iso).getTime()) / 1000));
  if (s < 60) return `${s}s ago`;
  if (s < 3600) return `${Math.floor(s / 60)} min ago`;
  if (s < 86400) return `${Math.floor(s / 3600)} h ago`;
  return `${Math.floor(s / 86400)} d ago`;
}

export function download(filename, text, type = 'text/markdown') {
  const url = URL.createObjectURL(new Blob([text], { type }));
  const a = document.createElement('a');
  a.href = url;
  a.download = filename;
  a.click();
  URL.revokeObjectURL(url);
}
