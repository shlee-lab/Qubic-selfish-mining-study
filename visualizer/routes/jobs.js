// routes/jobs.js
const express = require('express');
const chokidar = require('chokidar');
const { RAW_JOBS_CSV_PATH } = require('../config/paths');
const { readFileSafe, parseCsvSimple } = require('../utils/io');

const router = express.Router();

// GET raw CSV
router.get('/api/jobs.csv', (_req, res) => {
  const data = readFileSafe(RAW_JOBS_CSV_PATH);
  res.set('Content-Type', 'text/csv; charset=utf-8');
  res.set('Cache-Control', 'no-store');
  res.send(data);
});

// GET parsed JSON
router.get('/api/jobs', (_req, res) => {
  const parsed = parseCsvSimple(readFileSafe(RAW_JOBS_CSV_PATH));
  res.set('Cache-Control', 'no-store');
  res.json({ ts: Date.now(), ...parsed });
});

// SSE stream
router.get('/api/jobs/stream', (req, res) => {
  res.set({
    'Content-Type': 'text/event-stream; charset=utf-8',
    'Cache-Control': 'no-store',
    'Connection': 'keep-alive',
  });
  if (typeof res.flushHeaders === 'function') res.flushHeaders();

  const push = () => {
    const csv = readFileSafe(RAW_JOBS_CSV_PATH);
    res.write('event: jobs\n');
    res.write(`data: ${JSON.stringify({ ts: Date.now(), csv })}\n\n`);
  };

  push();
  const watcher = chokidar.watch(RAW_JOBS_CSV_PATH, { ignoreInitial: true });
  watcher.on('add', push).on('change', push);

  req.on('close', () => {
    try { watcher.close(); } catch {}
    res.end();
  });
});

module.exports = router;

