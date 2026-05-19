import React, { useEffect, useMemo, useState } from 'react';
import { createRoot } from 'react-dom/client';
import './styles.css';

const METERS = ['FM001', 'FM002'];
const POLL_MS = 10000;
const API_BASE = (import.meta.env.VITE_API_BASE || '').replace(/\/$/, '');

function endpoint(path) {
  return `${API_BASE}${path}`;
}

async function fetchJson(path, signal) {
  const response = await fetch(endpoint(path), {
    signal,
    headers: { Accept: 'application/json' },
  });
  if (!response.ok) {
    throw new Error(`HTTP ${response.status}`);
  }
  return response.json();
}

function toNumber(value) {
  const number = Number(value);
  return Number.isFinite(number) ? number : null;
}

function formatNumber(value, digits = 2) {
  const number = toNumber(value);
  return number === null ? '--' : number.toLocaleString(undefined, { maximumFractionDigits: digits });
}

function formatTime(value) {
  if (!value) return '--';
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return String(value);
  return date.toLocaleString(undefined, {
    month: '2-digit',
    day: '2-digit',
    hour: '2-digit',
    minute: '2-digit',
  });
}

function normalizeLatest(payload) {
  const rows = Array.isArray(payload)
    ? payload
    : Array.isArray(payload?.meters)
      ? payload.meters
      : Array.isArray(payload?.data)
        ? payload.data
        : METERS.map((id) => ({ meter_id: id, ...(payload?.[id] || {}) }));

  const byId = Object.fromEntries(METERS.map((id) => [id, { meter_id: id }]));
  rows.forEach((row) => {
    const id = row?.meter_id || row?.id || row?.meterId;
    if (METERS.includes(id)) {
      byId[id] = { ...byId[id], ...row, meter_id: id };
    }
  });
  return byId;
}

function normalizeIntervals(payload) {
  const rows = Array.isArray(payload)
    ? payload
    : Array.isArray(payload?.intervals)
      ? payload.intervals
      : Array.isArray(payload?.items)
        ? payload.items
        : Array.isArray(payload?.data)
          ? payload.data
          : [];

  return rows.map((row, index) => ({
    id: row.id || `${row.meter_id || row.meterId || 'meter'}-${row.window_start || row.start_time || index}`,
    meter_id: row.meter_id || row.meterId,
    window_start: row.window_start || row.start_time || row.interval_start || row.ts,
    window_end: row.window_end || row.end_time || row.interval_end,
    increment: toNumber(row.interval_usage ?? row.increment ?? row.interval_increment ?? row.flow_increment ?? row.delta_flow),
    avg_flow: toNumber(row.avg_instant_flow ?? row.avg_flow ?? row.average_flow ?? row.instant_flow_avg),
    max_flow: toNumber(row.max_instant_flow ?? row.max_flow ?? row.instant_flow_max),
    min_flow: toNumber(row.min_instant_flow ?? row.min_flow ?? row.instant_flow_min),
    anomaly: Boolean(row.anomaly || row.has_anomaly || row.has_gap || !['', 'valid', 'normal'].includes(String(row.status || '').toLowerCase())),
    status: row.status || row.anomaly_type || '',
  }));
}

function isOnline(meter) {
  if (typeof meter.online === 'boolean') return meter.online;
  if (typeof meter.is_online === 'boolean') return meter.is_online;
  if (meter.status) return !['offline', 'unknown'].includes(String(meter.status).toLowerCase());
  return false;
}

function hasAnomaly(meter) {
  return Boolean(meter.anomaly || meter.has_anomaly || meter.anomaly_type || meter.anomaly_reason || !['valid', 'online', 'unknown', undefined, null].includes(meter.status));
}

function App() {
  const [latest, setLatest] = useState(() => normalizeLatest({}));
  const [latestError, setLatestError] = useState('');
  const [lastRefresh, setLastRefresh] = useState(null);
  const [selectedMeter, setSelectedMeter] = useState(METERS[0]);
  const [intervals, setIntervals] = useState([]);
  const [historyError, setHistoryError] = useState('');
  const [loadingHistory, setLoadingHistory] = useState(false);

  useEffect(() => {
    let mounted = true;
    let controller;

    async function loadLatest() {
      controller?.abort();
      controller = new AbortController();
      try {
        const payload = await fetchJson('/api/meters/latest', controller.signal);
        if (!mounted) return;
        setLatest(normalizeLatest(payload));
        setLatestError('');
        setLastRefresh(new Date());
      } catch (error) {
        if (!mounted || error.name === 'AbortError') return;
        setLatestError(error.message || 'Unable to load latest readings');
      }
    }

    loadLatest();
    const timer = window.setInterval(loadLatest, POLL_MS);
    return () => {
      mounted = false;
      window.clearInterval(timer);
      controller?.abort();
    };
  }, []);

  useEffect(() => {
    const controller = new AbortController();
    setLoadingHistory(true);
    fetchJson(`/api/intervals?meter_id=${encodeURIComponent(selectedMeter)}&limit=96`, controller.signal)
      .then((payload) => {
        setIntervals(normalizeIntervals(payload));
        setHistoryError('');
      })
      .catch((error) => {
        if (error.name !== 'AbortError') {
          setIntervals([]);
          setHistoryError(error.message || 'Unable to load intervals');
        }
      })
      .finally(() => setLoadingHistory(false));
    return () => controller.abort();
  }, [selectedMeter]);

  const maxIncrement = useMemo(() => {
    return Math.max(1, ...intervals.map((row) => row.increment || 0));
  }, [intervals]);

  return (
    <main className="app-shell">
      <header className="topbar">
        <div>
          <p className="eyebrow">MQTT Flow Monitor</p>
          <h1>Flow meter operations</h1>
        </div>
        <div className="refresh-box">
          <span className={latestError ? 'dot danger' : 'dot ok'} />
          <div>
            <strong>{latestError ? 'API degraded' : 'Live polling'}</strong>
            <span>{lastRefresh ? `Updated ${formatTime(lastRefresh)}` : 'Waiting for first sample'}</span>
          </div>
        </div>
      </header>

      {latestError && <StatusBanner tone="warning" text={`Latest readings unavailable: ${latestError}`} />}

      <section className="meter-grid" aria-label="Latest meter readings">
        {METERS.map((id) => (
          <MeterCard
            key={id}
            meter={latest[id]}
            selected={selectedMeter === id}
            onSelect={() => setSelectedMeter(id)}
          />
        ))}
      </section>

      <section className="history-section">
        <div className="section-head">
          <div>
            <p className="eyebrow">15-minute intervals</p>
            <h2>{selectedMeter} history</h2>
          </div>
          <div className="meter-switch" role="tablist" aria-label="Select meter history">
            {METERS.map((id) => (
              <button
                key={id}
                type="button"
                className={selectedMeter === id ? 'active' : ''}
                onClick={() => setSelectedMeter(id)}
              >
                {id}
              </button>
            ))}
          </div>
        </div>

        {historyError && <StatusBanner tone="warning" text={`History unavailable: ${historyError}`} />}

        <div className="history-layout">
          <div className="bars-panel">
            {loadingHistory ? (
              <EmptyState title="Loading intervals" text="Fetching the latest 96 windows." />
            ) : intervals.length ? (
              <div className="bars" aria-label="Interval increment bars">
                {intervals.slice(-32).map((row) => (
                  <div
                    key={row.id}
                    className={`bar ${row.anomaly ? 'anomaly' : ''}`}
                    style={{ height: `${Math.max(5, ((row.increment || 0) / maxIncrement) * 100)}%` }}
                    title={`${formatTime(row.window_start)}: ${formatNumber(row.increment)} m3`}
                  />
                ))}
              </div>
            ) : (
              <EmptyState title="No interval data" text="The backend returned no 15-minute records yet." />
            )}
          </div>

          <div className="table-wrap">
            <table>
              <thead>
                <tr>
                  <th>Window</th>
                  <th>Increment</th>
                  <th>Avg flow</th>
                  <th>Range</th>
                  <th>Status</th>
                </tr>
              </thead>
              <tbody>
                {intervals.length ? (
                  intervals.map((row) => (
                    <tr key={row.id}>
                      <td>
                        <span className="primary">{formatTime(row.window_start)}</span>
                        <span className="subtle">{row.window_end ? `to ${formatTime(row.window_end)}` : '15-min window'}</span>
                      </td>
                      <td>{formatNumber(row.increment)} m3</td>
                      <td>{formatNumber(row.avg_flow)} m3/h</td>
                      <td>{formatNumber(row.min_flow)} - {formatNumber(row.max_flow)}</td>
                      <td>
                        <span className={row.anomaly ? 'pill danger' : 'pill ok'}>
                          {row.anomaly ? row.status || 'Anomaly' : 'Normal'}
                        </span>
                      </td>
                    </tr>
                  ))
                ) : (
                  <tr>
                    <td colSpan="5" className="empty-row">
                      {loadingHistory ? 'Loading...' : 'No history records to display.'}
                    </td>
                  </tr>
                )}
              </tbody>
            </table>
          </div>
        </div>
      </section>
    </main>
  );
}

function MeterCard({ meter, selected, onSelect }) {
  const online = isOnline(meter);
  const anomaly = hasAnomaly(meter);
  const recentIncrement = meter.recent_interval_usage ?? meter.recent_15m_increment ?? meter.last_15m_increment ?? meter.interval_increment;
  const todayTotal = meter.today_usage ?? meter.today_total ?? meter.today_flow ?? meter.daily_total;
  const timestamp = meter.last_device_ts || meter.last_received_ts || meter.device_ts || meter.server_ts || meter.received_at || meter.updated_at;

  return (
    <button type="button" className={`meter-card ${selected ? 'selected' : ''}`} onClick={onSelect}>
      <div className="card-head">
        <div>
          <span className="meter-id">{meter.meter_id}</span>
          <span className="subtle">{formatTime(timestamp)}</span>
        </div>
        <span className={online ? 'pill ok' : 'pill muted'}>{online ? 'Online' : 'Offline'}</span>
      </div>

      <div className="metric-main">
        <span>{formatNumber(meter.instant_flow)}</span>
        <small>m3/h instant</small>
      </div>

      <div className="metric-grid">
        <Metric label="Total" value={`${formatNumber(meter.total_flow)} m3`} />
        <Metric label="Last 15 min" value={`${formatNumber(recentIncrement)} m3`} />
        <Metric label="Today" value={`${formatNumber(todayTotal)} m3`} />
        <Metric label="Anomaly" value={anomaly ? (meter.anomaly_reason || meter.status || 'Check') : 'Clear'} danger={anomaly} />
      </div>
    </button>
  );
}

function Metric({ label, value, danger }) {
  return (
    <div className="metric">
      <span>{label}</span>
      <strong className={danger ? 'danger-text' : ''}>{value}</strong>
    </div>
  );
}

function StatusBanner({ text }) {
  return (
    <div className="status-banner" role="status">
      {text}
    </div>
  );
}

function EmptyState({ title, text }) {
  return (
    <div className="empty-state">
      <strong>{title}</strong>
      <span>{text}</span>
    </div>
  );
}

createRoot(document.getElementById('root')).render(<App />);
