// routes/blocks.js
const express = require('express');
const chokidar = require('chokidar');
const { BLOCKS_CSV_PATH } = require('../config/paths');
const { readFileSafe, parseCsvSimple } = require('../utils/io');
const { collapseByHashChange } = require('../utils/blocks');

const router = express.Router();

// CSV
router.get('/api/blocks.csv', (_req, res) => {
  const data = readFileSafe(BLOCKS_CSV_PATH);
  res.set('Content-Type', 'text/csv; charset=utf-8');
  res.set('Cache-Control', 'no-store');
  res.send(data);
});

// JSON
router.get('/api/blocks', (_req, res) => {
  const parsed = parseCsvSimple(readFileSafe(BLOCKS_CSV_PATH));
  res.set('Cache-Control', 'no-store');
  res.json({ ts: Date.now(), ...parsed });
});

// uniq
router.get('/api/blocks/uniq', (_req, res) => {
  const parsed = parseCsvSimple(readFileSafe(BLOCKS_CSV_PATH));
  const uniq = collapseByHashChange(parsed.header, parsed.rows);
  res.set('Cache-Control', 'no-store');
  res.json({ ts: Date.now(), ...uniq });
});

// SSE
router.get('/api/blocks/stream', (req, res) => {
  res.set({
    'Content-Type': 'text/event-stream; charset=utf-8',
    'Cache-Control': 'no-store',
    'Connection': 'keep-alive',
  });
  if (typeof res.flushHeaders === 'function') res.flushHeaders();

  const push = () => {
    const csv = readFileSafe(BLOCKS_CSV_PATH);
    const parsed = parseCsvSimple(csv);
    const uniq = collapseByHashChange(parsed.header, parsed.rows);
    res.write('event: blocks\n');
    res.write(`data: ${JSON.stringify({ ts: Date.now(), csv, parsed, uniq })}\n\n`);
  };

  push();
  const watcher = chokidar.watch(BLOCKS_CSV_PATH, { ignoreInitial: true });
  watcher.on('add', push).on('change', push);

  req.on('close', () => {
    try { watcher.close(); } catch {}
    res.end();
  });
});

module.exports = router;

