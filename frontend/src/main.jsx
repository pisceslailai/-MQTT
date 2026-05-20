import React, { useEffect, useMemo, useState } from 'react';
import { createRoot } from 'react-dom/client';
import './styles.css';

const METERS = ['FM001', 'FM002'];
const POLL_MS = 10000;
const API_BASE = (import.meta.env.VITE_API_BASE || '').replace(/\/$/, '');
const STATUS_TEXT = {
  valid: '正常',
  normal: '正常',
  online: '在线',
  offline: '离线',
  unknown: '未知',
  gap: '缺数据',
  clock_skew: '时钟偏差',
  counter_reset: '累计量回退',
  anomaly: '异常',
};

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

function statusText(value, fallback = '正常') {
  if (!value) return fallback;
  const key = String(value).toLowerCase();
  return STATUS_TEXT[key] || String(value);
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
        setLatestError(error.message || '无法加载实时数据');
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
          setHistoryError(error.message || '无法加载 15 分钟记录');
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
          <p className="eyebrow">MQTT 流量监控</p>
          <h1>流量计运行看板</h1>
        </div>
        <div className="refresh-box">
          <span className={latestError ? 'dot danger' : 'dot ok'} />
          <div>
            <strong>{latestError ? '接口异常' : '实时轮询中'}</strong>
            <span>{lastRefresh ? `更新时间 ${formatTime(lastRefresh)}` : '等待首条数据'}</span>
          </div>
        </div>
      </header>

      {latestError && <StatusBanner text={`实时数据不可用：${latestError}`} />}

      <section className="meter-grid" aria-label="流量计实时读数">
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
            <p className="eyebrow">15 分钟结算记录</p>
            <h2>{selectedMeter} 历史趋势</h2>
          </div>
          <div className="meter-switch" role="tablist" aria-label="选择流量计历史数据">
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

        {historyError && <StatusBanner text={`历史数据不可用：${historyError}`} />}

        <div className="history-layout">
          <div className="bars-panel">
            {loadingHistory ? (
              <EmptyState title="正在加载" text="正在读取最近 96 个 15 分钟窗口。" />
            ) : intervals.length ? (
              <div className="bars" aria-label="15 分钟用量柱状图">
                {intervals.slice(-32).map((row) => (
                  <div
                    key={row.id}
                    className={`bar ${row.anomaly ? 'anomaly' : ''}`}
                    style={{ height: `${Math.max(5, ((row.increment || 0) / maxIncrement) * 100)}%` }}
                    title={`${formatTime(row.window_start)}：${formatNumber(row.increment)} m3`}
                  />
                ))}
              </div>
            ) : (
              <EmptyState title="暂无结算数据" text="后端还没有生成 15 分钟记录。" />
            )}
          </div>

          <div className="table-wrap">
            <table>
              <thead>
                <tr>
                  <th>时间窗口</th>
                  <th>增量</th>
                  <th>平均瞬时流量</th>
                  <th>瞬时范围</th>
                  <th>状态</th>
                </tr>
              </thead>
              <tbody>
                {intervals.length ? (
                  intervals.map((row) => (
                    <tr key={row.id}>
                      <td>
                        <span className="primary">{formatTime(row.window_start)}</span>
                        <span className="subtle">{row.window_end ? `至 ${formatTime(row.window_end)}` : '15 分钟窗口'}</span>
                      </td>
                      <td>{formatNumber(row.increment)} m3</td>
                      <td>{formatNumber(row.avg_flow)} m3/h</td>
                      <td>{formatNumber(row.min_flow)} - {formatNumber(row.max_flow)}</td>
                      <td>
                        <span className={row.anomaly ? 'pill danger' : 'pill ok'}>
                          {row.anomaly ? statusText(row.status, '异常') : '正常'}
                        </span>
                      </td>
                    </tr>
                  ))
                ) : (
                  <tr>
                    <td colSpan="5" className="empty-row">
                      {loadingHistory ? '加载中...' : '暂无历史记录。'}
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
        <span className={online ? 'pill ok' : 'pill muted'}>{online ? '在线' : '离线'}</span>
      </div>

      <div className="metric-main">
        <span>{formatNumber(meter.instant_flow)}</span>
        <small>m3/h 瞬时流量</small>
      </div>

      <div className="metric-grid">
        <Metric label="累计流量" value={`${formatNumber(meter.total_flow)} m3`} />
        <Metric label="最近15分钟" value={`${formatNumber(recentIncrement)} m3`} />
        <Metric label="今日累计" value={`${formatNumber(todayTotal)} m3`} />
        <Metric label="异常状态" value={anomaly ? (meter.anomaly_reason || statusText(meter.status, '待检查')) : '正常'} danger={anomaly} />
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
