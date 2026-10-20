import { CartesianGrid, Legend, Line, LineChart, ReferenceArea, ReferenceLine, ResponsiveContainer, Tooltip, XAxis, YAxis } from 'recharts';
import { SENSOR_COLOR, SENSOR_LABEL, SENSOR_UNIT, fmtShort } from '../util.js';

// One chart per sensor so different units are never plotted on a shared axis.
export default function SensorChart({ parameter, points, thresholds, hour12 }) {
  const th = thresholds?.[parameter];
  const label = `${SENSOR_LABEL[parameter]} (${SENSOR_UNIT[parameter]})`;
  const data = points.map((p) => ({ t: new Date(p.recorded_at).getTime(), v: p[parameter] }));
  const values = data.map((d) => d.v);
  let lo = Math.min(...values), hi = Math.max(...values);
  if (th) { lo = Math.min(lo, th.pref_min, th.warn_low); hi = Math.max(hi, th.pref_max, th.warn_high); }
  const pad = Math.max((hi - lo) * 0.1, 1);
  const spanMs = data.length ? data[data.length - 1].t - data[0].t : 0;
  const fmtTick = (t) => new Date(t).toLocaleString(undefined, spanMs > 2 * 86400000
    ? { month: 'short', day: '2-digit' } : { hour: '2-digit', minute: '2-digit', hour12 });

  return (
    <figure style={{ margin: 0 }} aria-label={`${label} history chart`}>
      <figcaption className="small muted" style={{ padding: '0 14px' }}>{label} · simulated data{th ? ' · shaded band = preferred range' : ''}</figcaption>
      <div className="chart-box">
        <ResponsiveContainer width="100%" height="100%">
          <LineChart data={data} margin={{ top: 8, right: 16, bottom: 4, left: 0 }}>
            <CartesianGrid stroke="#e4e7dc" strokeDasharray="3 3" />
            <XAxis dataKey="t" type="number" scale="time" domain={['dataMin', 'dataMax']} tickFormatter={fmtTick} tick={{ fontSize: 11 }} minTickGap={40} />
            <YAxis domain={[Math.floor(lo - pad), Math.ceil(hi + pad)]} tick={{ fontSize: 11 }} width={40}
              label={{ value: SENSOR_UNIT[parameter], angle: -90, position: 'insideLeft', fontSize: 11, offset: 12 }} />
            {th && <ReferenceArea y1={th.pref_min} y2={th.pref_max} fill="#a8c8b0" fillOpacity={0.3} ifOverflow="extendDomain" />}
            {th && <ReferenceLine y={th.warn_low} stroke="#8a5a00" strokeDasharray="4 3" ifOverflow="extendDomain" label={{ value: 'warning', fontSize: 10, fill: '#8a5a00', position: 'insideBottomRight' }} />}
            {th && th.warn_high !== th.pref_max && <ReferenceLine y={th.warn_high} stroke="#8a5a00" strokeDasharray="4 3" ifOverflow="extendDomain" />}
            <Tooltip labelFormatter={(t) => fmtShort(new Date(t).toISOString(), hour12)} formatter={(v) => [`${v} ${SENSOR_UNIT[parameter]}`, SENSOR_LABEL[parameter]]} />
            <Legend verticalAlign="top" height={20} iconType="plainline" formatter={() => SENSOR_LABEL[parameter]} />
            <Line type="monotone" dataKey="v" stroke={SENSOR_COLOR[parameter]} strokeWidth={2} dot={data.length < 40} isAnimationActive={false} />
          </LineChart>
        </ResponsiveContainer>
      </div>
    </figure>
  );
}
