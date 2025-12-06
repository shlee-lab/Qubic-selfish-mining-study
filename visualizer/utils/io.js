// utils/io.js
const fs = require('fs');

function readFileSafe(p) {
  try { return fs.readFileSync(p, 'utf-8'); }
  catch { return ''; }
}

function parseCsvSimple(csv) {
  const text = (csv || '').trim();
  if (!text) return { header: [], rows: [] };
  const lines = text.split(/\r?\n/).filter(Boolean);
  const header = lines[0].split(',');
  const rows = lines.slice(1).map(l => l.split(','));
  return { header, rows };
}

module.exports = { readFileSafe, parseCsvSimple };

