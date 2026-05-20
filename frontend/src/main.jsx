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
  return number === null ? '--' : number.toLocaleString('zh-CN', { maximumFractionDigits: digits });
}

function formatTime(value) {
  if (!value) return '--';
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return String(value);
  return date.toLocaleString('zh-CN', {
    month: '2-digit',
    day: '2-digit',
    hour: '2-digit',
    minute: '2-digit',
  });
}

function toDateInputValue(date) {
  const local = new Date(date.getTime() - date.getTimezoneOffset() * 60000);
  return local.toISOString().slice(0, 16);
}

function toQueryTime(value) {
  if (!value) return '';
  const date = new Date(value);
  return Number.isNaN(date.getTime()) ? '' : date.toISOString();
}

function defaultRange(hours = 24) {
  const end = new Date();
  const start = new Date(end.getTime() - hours * 60 * 60 * 1000);
  return {
    start: toDateInputValue(start),
    end: toDateInputValue(end),
  };
}

function statusText(value, fallback = '正常') {
  if (!value) return fallback;
  const key = String(value).toLowerCase();
  return STATUS_TEXT[key] || String(value);
}

function isProblemStatus(value) {
  return !['', 'valid', 'normal'].includes(String(value || '').toLowerCase());
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
      : [];

  return rows.map((row, index) => ({
    id: row.id || `${row.meter_id || 'meter'}-${row.window_start || index}`,
    meter_id: row.meter_id,
    window_start: row.window_start,
    window_end: row.window_end,
    increment: toNumber(row.interval_usage),
    avg_flow: toNumber(row.avg_instant_flow),
    max_flow: toNumber(row.max_instant_flow),
    min_flow: toNumber(row.min_instant_flow),
    sample_count: toNumber(row.sample_count),
    has_gap: Boolean(row.has_gap),
    status: row.status || '',
    anomaly: Boolean(row.has_gap || isProblemStatus(row.status)),
  }));
}

function normalizeRaw(payload) {
  const rows = Array.isArray(payload)
    ? payload
    : Array.isArray(payload?.readings)
      ? payload.readings
      : [];

  return rows.map((row) => ({
    id: row.id,
    meter_id: row.meter_id,
    device_ts: row.device_ts,
    received_ts: row.received_ts,
    instant_flow: toNumber(row.instant_flow),
    total_flow: toNumber(row.total_flow),
    unit: row.unit || 'm3/h',
    status: row.status || '',
    anomaly_reason: row.anomaly_reason || '',
  }));
}

function isOnline(meter) {
  if (typeof meter.online === 'boolean') return meter.online;
  if (meter.status) return !['offline', 'unknown'].includes(String(meter.status).toLowerCase());
  return false;
}

function hasAnomaly(meter) {
  return Boolean(meter.anomaly_reason || !['valid', 'online', 'unknown', undefined, null].includes(meter.status));
}

function buildQuery(params) {
  const search = new URLSearchParams();
  Object.entries(params).forEach(([key, value]) => {
    if (value !== undefined && value !== null && value !== '') {
      search.set(key, value);
    }
  });
  return search.toString();
}

function csvEscape(value) {
  const text = value === null || value === undefined ? '' : String(value);
  return `"${text.replace(/"/g, '""')}"`;
}

function downloadCsv(filename, rows, columns) {
  const content = [
    columns.map((column) => csvEscape(column.label)).join(','),
    ...rows.map((row) => columns.map((column) => csvEscape(column.value(row))).join(',')),
  ].join('\n');
  const blob = new Blob([`\ufeff${content}`], { type: 'text/csv;charset=utf-8' });
  const url = URL.createObjectURL(blob);
  const anchor = document.createElement('a');
  anchor.href = url;
  anchor.download = filename;
  anchor.click();
  URL.revokeObjectURL(url);
}

function App() {
  const initialRange = useMemo(() => defaultRange(24), []);
  const [latest, setLatest] = useState(() => normalizeLatest({}));
  const [latestError, setLatestError] = useState('');
  const [lastRefresh, setLastRefresh] = useState(null);
  const [selectedMeter, setSelectedMeter] = useState(METERS[0]);
  const [startTime, setStartTime] = useState(initialRange.start);
  const [endTime, setEndTime] = useState(initialRange.end);
  const [statusFilter, setStatusFilter] = useState('');
  const [activeView, setActiveView] = useState('trend');
  const [intervals, setIntervals] = useState([]);
  const [rawReadings, setRawReadings] = useState([]);
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

  async function loadHistory(signal) {
    const common = {
      meter_id: selectedMeter,
      start: toQueryTime(startTime),
      end: toQueryTime(endTime),
      status: statusFilter,
    };
    const intervalQuery = buildQuery({ ...common, limit: 500 });
    const rawQuery = buildQuery({ ...common, limit: 500 });
    const [intervalPayload, rawPayload] = await Promise.all([
      fetchJson(`/api/intervals?${intervalQuery}`, signal),
      fetchJson(`/api/readings/recent?${rawQuery}`, signal),
    ]);
    setIntervals(normalizeIntervals(intervalPayload));
    setRawReadings(normalizeRaw(rawPayload));
  }

  useEffect(() => {
    const controller = new AbortController();
    setLoadingHistory(true);
    loadHistory(controller.signal)
      .then(() => setHistoryError(''))
      .catch((error) => {
        if (error.name !== 'AbortError') {
          setIntervals([]);
          setRawReadings([]);
          setHistoryError(error.message || '无法加载历史数据');
        }
      })
      .finally(() => setLoadingHistory(false));
    return () => controller.abort();
  }, [selectedMeter]);

  function applyQuickRange(hours) {
    const range = defaultRange(hours);
    setStartTime(range.start);
    setEndTime(range.end);
  }

  function handleSearch(event) {
    event.preventDefault();
    const controller = new AbortController();
    setLoadingHistory(true);
    loadHistory(controller.signal)
      .then(() => setHistoryError(''))
      .catch((error) => setHistoryError(error.message || '无法加载历史数据'))
      .finally(() => setLoadingHistory(false));
  }

  const summary = useMemo(() => summarizeIntervals(intervals, rawReadings), [intervals, rawReadings]);

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
            <p className="eyebrow">历史数据查询</p>
            <h2>{selectedMeter} 多维分析</h2>
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

        <form className="query-panel" onSubmit={handleSearch}>
          <label>
            <span>开始时间</span>
            <input type="datetime-local" value={startTime} onChange={(event) => setStartTime(event.target.value)} />
          </label>
          <label>
            <span>结束时间</span>
            <input type="datetime-local" value={endTime} onChange={(event) => setEndTime(event.target.value)} />
          </label>
          <label>
            <span>状态筛选</span>
            <select value={statusFilter} onChange={(event) => setStatusFilter(event.target.value)}>
              <option value="">全部状态</option>
              <option value="valid">正常</option>
              <option value="gap">缺数据</option>
              <option value="clock_skew">时钟偏差</option>
              <option value="counter_reset">累计量回退</option>
            </select>
          </label>
          <div className="quick-range">
            <button type="button" onClick={() => applyQuickRange(6)}>近6小时</button>
            <button type="button" onClick={() => applyQuickRange(24)}>近24小时</button>
            <button type="button" onClick={() => applyQuickRange(24 * 7)}>近7天</button>
          </div>
          <button type="submit" className="primary-action">{loadingHistory ? '查询中' : '查询'}</button>
        </form>

        {historyError && <StatusBanner text={`历史数据不可用：${historyError}`} />}

        <SummaryGrid summary={summary} />

        <div className="view-tabs" role="tablist" aria-label="历史数据展示方式">
          <button type="button" className={activeView === 'trend' ? 'active' : ''} onClick={() => setActiveView('trend')}>趋势图</button>
          <button type="button" className={activeView === 'bars' ? 'active' : ''} onClick={() => setActiveView('bars')}>柱状图</button>
          <button type="button" className={activeView === 'intervals' ? 'active' : ''} onClick={() => setActiveView('intervals')}>结算表</button>
          <button type="button" className={activeView === 'raw' ? 'active' : ''} onClick={() => setActiveView('raw')}>原始明细</button>
          <button type="button" onClick={() => exportCurrent(activeView, intervals, rawReadings, selectedMeter)}>导出CSV</button>
        </div>

        <HistoryView
          activeView={activeView}
          intervals={intervals}
          rawReadings={rawReadings}
          loading={loadingHistory}
        />
      </section>
    </main>
  );
}

function summarizeIntervals(intervals, rawReadings) {
  const totalUsage = intervals.reduce((sum, row) => sum + (row.increment || 0), 0);
  const avgFlowValues = intervals.map((row) => row.avg_flow).filter((value) => value !== null);
  const avgFlow = avgFlowValues.length ? avgFlowValues.reduce((sum, value) => sum + value, 0) / avgFlowValues.length : null;
  const peakFlow = Math.max(0, ...intervals.map((row) => row.max_flow || 0));
  const problemCount = intervals.filter((row) => row.anomaly).length + rawReadings.filter((row) => isProblemStatus(row.status)).length;
  return {
    totalUsage,
    avgFlow,
    peakFlow,
    intervalCount: intervals.length,
    rawCount: rawReadings.length,
    problemCount,
  };
}

function SummaryGrid({ summary }) {
  return (
    <div className="summary-grid">
      <MetricBox label="区间总用量" value={`${formatNumber(summary.totalUsage)} m3`} />
      <MetricBox label="平均瞬时流量" value={`${formatNumber(summary.avgFlow)} m3/h`} />
      <MetricBox label="峰值瞬时流量" value={`${formatNumber(summary.peakFlow)} m3/h`} />
      <MetricBox label="15分钟记录" value={`${summary.intervalCount} 条`} />
      <MetricBox label="原始读数" value={`${summary.rawCount} 条`} />
      <MetricBox label="异常/缺口" value={`${summary.problemCount} 条`} danger={summary.problemCount > 0} />
    </div>
  );
}

function HistoryView({ activeView, intervals, rawReadings, loading }) {
  if (loading) {
    return <EmptyState title="正在加载" text="正在读取历史数据。" />;
  }

  if (activeView === 'trend') {
    return <LineChart rows={intervals} />;
  }
  if (activeView === 'bars') {
    return <BarChart rows={intervals} />;
  }
  if (activeView === 'raw') {
    return <RawTable rows={rawReadings} />;
  }
  return <IntervalTable rows={intervals} />;
}

function LineChart({ rows }) {
  if (!rows.length) {
    return <EmptyState title="暂无趋势数据" text="请调整时间范围或等待网关上报。" />;
  }
  const width = 900;
  const height = 280;
  const padding = 28;
  const values = rows.map((row) => row.increment || 0);
  const max = Math.max(1, ...values);
  const points = rows.map((row, index) => {
    const x = rows.length === 1 ? width / 2 : padding + (index / (rows.length - 1)) * (width - padding * 2);
    const y = height - padding - ((row.increment || 0) / max) * (height - padding * 2);
    return { x, y, row };
  });
  const path = points.map((point, index) => `${index === 0 ? 'M' : 'L'} ${point.x} ${point.y}`).join(' ');

  return (
    <div className="chart-card">
      <div className="chart-head">
        <strong>15分钟增量趋势</strong>
        <span>按时间顺序展示每个结算窗口用量</span>
      </div>
      <svg className="line-chart" viewBox={`0 0 ${width} ${height}`} role="img" aria-label="15分钟增量趋势图">
        <line x1={padding} y1={height - padding} x2={width - padding} y2={height - padding} />
        <line x1={padding} y1={padding} x2={padding} y2={height - padding} />
        <path d={path} />
        {points.map((point) => (
          <circle key={point.row.id} cx={point.x} cy={point.y} r="4">
            <title>{`${formatTime(point.row.window_start)}：${formatNumber(point.row.increment)} m3`}</title>
          </circle>
        ))}
      </svg>
    </div>
  );
}

function BarChart({ rows }) {
  if (!rows.length) {
    return <EmptyState title="暂无柱状图数据" text="请调整时间范围或等待网关上报。" />;
  }
  const max = Math.max(1, ...rows.map((row) => row.increment || 0));
  return (
    <div className="chart-card">
      <div className="chart-head">
        <strong>15分钟用量柱状图</strong>
        <span>红色表示缺口或异常窗口</span>
      </div>
      <div className="bars large" aria-label="15分钟用量柱状图">
        {rows.slice(-96).map((row) => (
          <div
            key={row.id}
            className={`bar ${row.anomaly ? 'anomaly' : ''}`}
            style={{ height: `${Math.max(4, ((row.increment || 0) / max) * 100)}%` }}
            title={`${formatTime(row.window_start)}：${formatNumber(row.increment)} m3`}
          />
        ))}
      </div>
    </div>
  );
}

function IntervalTable({ rows }) {
  return (
    <DataTable emptyText="暂无15分钟结算记录。">
      <thead>
        <tr>
          <th>时间窗口</th>
          <th>增量</th>
          <th>平均瞬时流量</th>
          <th>瞬时范围</th>
          <th>样本数</th>
          <th>状态</th>
        </tr>
      </thead>
      <tbody>
        {rows.map((row) => (
          <tr key={row.id}>
            <td>
              <span className="primary">{formatTime(row.window_start)}</span>
              <span className="subtle">{row.window_end ? `至 ${formatTime(row.window_end)}` : '15分钟窗口'}</span>
            </td>
            <td>{formatNumber(row.increment)} m3</td>
            <td>{formatNumber(row.avg_flow)} m3/h</td>
            <td>{formatNumber(row.min_flow)} - {formatNumber(row.max_flow)}</td>
            <td>{formatNumber(row.sample_count, 0)}</td>
            <td><StatusPill status={row.status} danger={row.anomaly} /></td>
          </tr>
        ))}
      </tbody>
      {!rows.length && <EmptyTableRow colSpan={6} text="暂无15分钟结算记录。" />}
    </DataTable>
  );
}

function RawTable({ rows }) {
  return (
    <DataTable emptyText="暂无原始读数。">
      <thead>
        <tr>
          <th>设备时间</th>
          <th>接收时间</th>
          <th>瞬时流量</th>
          <th>累计流量</th>
          <th>状态</th>
          <th>异常说明</th>
        </tr>
      </thead>
      <tbody>
        {rows.map((row) => (
          <tr key={row.id}>
            <td>{formatTime(row.device_ts)}</td>
            <td>{formatTime(row.received_ts)}</td>
            <td>{formatNumber(row.instant_flow)} m3/h</td>
            <td>{formatNumber(row.total_flow)} m3</td>
            <td><StatusPill status={row.status} danger={isProblemStatus(row.status)} /></td>
            <td>{row.anomaly_reason || '--'}</td>
          </tr>
        ))}
      </tbody>
      {!rows.length && <EmptyTableRow colSpan={6} text="暂无原始读数。" />}
    </DataTable>
  );
}

function DataTable({ children }) {
  return (
    <div className="table-wrap wide">
      <table>{children}</table>
    </div>
  );
}

function EmptyTableRow({ colSpan, text }) {
  return (
    <tbody>
      <tr>
        <td colSpan={colSpan} className="empty-row">{text}</td>
      </tr>
    </tbody>
  );
}

function StatusPill({ status, danger }) {
  return (
    <span className={danger ? 'pill danger' : 'pill ok'}>
      {statusText(status)}
    </span>
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

function MetricBox({ label, value, danger }) {
  return (
    <div className={`summary-box ${danger ? 'danger' : ''}`}>
      <span>{label}</span>
      <strong>{value}</strong>
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

function exportCurrent(activeView, intervals, rawReadings, selectedMeter) {
  if (activeView === 'raw') {
    downloadCsv(`${selectedMeter}-原始读数.csv`, rawReadings, [
      { label: '设备时间', value: (row) => row.device_ts },
      { label: '接收时间', value: (row) => row.received_ts },
      { label: '瞬时流量', value: (row) => row.instant_flow },
      { label: '累计流量', value: (row) => row.total_flow },
      { label: '状态', value: (row) => statusText(row.status) },
      { label: '异常说明', value: (row) => row.anomaly_reason },
    ]);
    return;
  }
  downloadCsv(`${selectedMeter}-15分钟结算.csv`, intervals, [
    { label: '窗口开始', value: (row) => row.window_start },
    { label: '窗口结束', value: (row) => row.window_end },
    { label: '增量', value: (row) => row.increment },
    { label: '平均瞬时流量', value: (row) => row.avg_flow },
    { label: '最小瞬时流量', value: (row) => row.min_flow },
    { label: '最大瞬时流量', value: (row) => row.max_flow },
    { label: '样本数', value: (row) => row.sample_count },
    { label: '状态', value: (row) => statusText(row.status) },
  ]);
}

createRoot(document.getElementById('root')).render(<App />);
