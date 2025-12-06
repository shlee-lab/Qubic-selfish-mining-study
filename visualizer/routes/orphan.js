const express = require('express');
const { BLOCKS_CSV_PATH, COUNT_ORPHAN_HTML } = require('../config/paths');
const { readFileSafe, parseCsvSimple } = require('../utils/io');

const router = express.Router();

// --- tiny helpers (no heavy error handling) ---
const tf = (v) => String(v ?? '').trim().toUpperCase() === 'TRUE';

function parseDateLoose(v) {
  const s = String(v ?? '').trim();
  if (/^-?\d+(\.\d+)?$/.test(s)) {
    const num = Number(s);
    const ms = num > 1e12 ? num : num * 1000; 
    return new Date(ms);
  }
  return new Date(s);
}
const dayKey = (d) => {
  const y = d.getUTCFullYear();
  const m = String(d.getUTCMonth() + 1).padStart(2, '0');
  const dd = String(d.getUTCDate()).padStart(2, '0');
  return `${y}-${m}-${dd}`;
};
const hourKey = (d) => {
  const y = d.getUTCFullYear();
  const m = String(d.getUTCMonth() + 1).padStart(2, '0');
  const dd = String(d.getUTCDate()).padStart(2, '0');
  const h = String(d.getUTCHours()).padStart(2, '0');
  return `${y}-${m}-${dd}T${h}:00:00Z`;
};
const clampIsoDate = (d) =>
  new Date(Date.UTC(d.getUTCFullYear(), d.getUTCMonth(), d.getUTCDate()))
    .toISOString()
    .slice(0, 10);

// --- index & range ---
function readIndex() {
  const csv = readFileSafe(BLOCKS_CSV_PATH);
  const { header, rows } = parseCsvSimple(csv);
  
  const lower = header.map((h) => String(h || '').trim().toLowerCase());
  const idx = {
    ts:  lower.indexOf('timestamp'),
    iso: lower.indexOf('is_orphan'),
    isq: lower.indexOf('is_qubic'),
  };
  return { rows, idx };
}

function parseRange(startStr, endStr) {
  const now = new Date();
  const today = new Date(Date.UTC(now.getUTCFullYear(), now.getUTCMonth(), now.getUTCDate()));
  const start = startStr ? new Date(startStr + 'T00:00:00Z') : new Date(today);
  const end   = endStr   ? new Date(endStr   + 'T23:59:59Z') : new Date(today);
  if (!startStr) start.setUTCDate(end.getUTCDate() - 13); // default: last 14 days
  return { start, end };
}

// --- aggregations ---
function aggregateDaily(rows, idx, start, end) {
  const by = new Map();
  for (const r of rows) {
    const d = parseDateLoose(r[idx.ts]);
    if (isNaN(d.getTime()) || d < start || d > end) continue;

    const key = dayKey(d);
    if (!by.has(key)) by.set(key, { date: key, total: 0, orphan: 0, orphan_qubic: 0 });

    const a = by.get(key);
    a.total += 1;

    if (tf(r[idx.iso])) {
      a.orphan += 1;
      if (tf(r[idx.isq])) a.orphan_qubic += 1;
    }
  }

  return Array.from(by.values())
    .sort((a, b) => a.date.localeCompare(b.date))
    .map((x) => ({
      ...x,
      rate_orphan: x.total ? +(x.orphan / x.total).toFixed(4) : 0,
      rate_orphan_qubic: x.total ? +(x.orphan_qubic / x.total).toFixed(4) : 0,
    }));
}

function aggregateHourly(rows, idx, start, end) {
  const by = new Map();
  for (const r of rows) {
    const d = parseDateLoose(r[idx.ts]);
    if (isNaN(d.getTime()) || d < start || d > end) continue;

    const key = hourKey(d);
    if (!by.has(key)) by.set(key, { ts: key, total: 0, orphan: 0, orphan_qubic: 0 });

    const a = by.get(key);
    a.total += 1;

    if (tf(r[idx.iso])) {
      a.orphan += 1;
      if (tf(r[idx.isq])) a.orphan_qubic += 1;
    }
  }
  return Array.from(by.values()).sort((a, b) => a.ts.localeCompare(b.ts));
}

function fallbackToLatest14(rows, idx, aggFn) {
  let latest = null;
  for (const r of rows) {
    const d = parseDateLoose(r[idx.ts]);
    if (!isNaN(d.getTime())) latest = latest && latest > d ? latest : d;
  }
  if (!latest) return { start: '', end: '', data: [] };
  const last = new Date(Date.UTC(latest.getUTCFullYear(), latest.getUTCMonth(), latest.getUTCDate()));
  const start = new Date(last); start.setUTCDate(last.getUTCDate() - 13);
  const end = new Date(last);   end.setUTCHours(23, 59, 59, 999);
  return { start, end, data: aggFn(start, end) };
}

// --- handlers ---
function handleDaily(req, res) {
  const { rows, idx } = readIndex();

  const { start, end } = parseRange(req.query.start, req.query.end);
  let data = aggregateDaily(rows, idx, start, end);

  if (!req.query.start && !req.query.end && data.length === 0) {
    const fb = fallbackToLatest14(rows, idx, (s, e) => aggregateDaily(rows, idx, s, e));
    return res
      .set('Cache-Control', 'no-store')
      .json({ ts: Date.now(), start: clampIsoDate(fb.start), end: clampIsoDate(fb.end), data: fb.data });
  }
  res.set('Cache-Control', 'no-store');
  return res.json({ ts: Date.now(), start: clampIsoDate(start), end: clampIsoDate(end), data });
}

function handleHourly(req, res) {
  const { rows, idx } = readIndex();

  const { start, end } = parseRange(req.query.start, req.query.end);
  let data = aggregateHourly(rows, idx, start, end);

  if (!req.query.start && !req.query.end && data.length === 0) {
    const fb = fallbackToLatest14(rows, idx, (s, e) => aggregateHourly(rows, idx, s, e));
    return res
      .set('Cache-Control', 'no-store')
      .json({ ts: Date.now(), start: clampIsoDate(fb.start), end: clampIsoDate(fb.end), data: fb.data });
  }
  res.set('Cache-Control', 'no-store');
  return res.json({ ts: Date.now(), start: clampIsoDate(start), end: clampIsoDate(end), data });
}

// --- routes ---
router.get('/api/orphan/daily', handleDaily);
router.get('/api/orphan/hourly', handleHourly);

// page
router.get('/count_orphan', (_req, res) => res.sendFile(COUNT_ORPHAN_HTML));

module.exports = router;
