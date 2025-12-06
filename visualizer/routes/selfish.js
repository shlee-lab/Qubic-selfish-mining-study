const fs = require('fs');
const express = require('express');
const router = express.Router();
const { BLOCKS_CSV_PATH } = require('../config/paths');
const { readFileSafe, parseCsvSimple } = require('../utils/io');

// --- tiny helpers (no defensive checks) ---
function normBoolTF(v) {
  const s = String(v).trim().toUpperCase();
  return s === 'TRUE';
}
function asInt(x) {
  const n = Number(String(x).replace(/,/g, '').trim());
  return n < 0 ? Math.ceil(n) : Math.floor(n);
}
function asIsoTs(v) {
  const s = String(v).trim();
  if (/^-?\d+(\.\d+)?$/.test(s)) {
    const num = Number(s);
    const ms = num > 1e12 ? num : num * 1000; // sec→ms heuristic
    return new Date(ms).toISOString();
  }
  return s;
}
function findConsecutiveRuns(sortedHeights, minLen = 3) {
  const runs=[]; let s=null, p=null;
  for (const h of sortedHeights){
    if (s===null){ s=h; p=h; continue; }
    if (h===p+1){ p=h; continue; }
    if (p-s+1>=minLen) runs.push([s,p]);
    s=h; p=h;
  }
  if (s!==null && p-s+1>=minLen) runs.push([s,p]);
  return runs;
}
function isQubicSelfishRun(s, e, mainByH) {
  for (let h=s; h<=e; h++){
    const m = mainByH.get(h);
    if (!m || m.is_qubic !== true) return false;
  }
  return true;
}

// ---- endpoints (assume file exists & header is correct) ----
router.get('/api/selfish-mining/meta', (_req, res) => {
  const st = fs.statSync(BLOCKS_CSV_PATH);
  const text = readFileSafe(BLOCKS_CSV_PATH);
  const head = (text.split(/\r?\n/)[0] || '').slice(0, 400);
  res.json({ BLOCKS_CSV_PATH, size_bytes: st.size, mtime: st.mtimeMs, head_line: head });
});

router.get('/api/selfish-mining', (req, res) => {
  const started = Date.now();
  const minRun = Math.max(2, Number(req.query.minRun || 3));

  const csv = readFileSafe(BLOCKS_CSV_PATH);
  const { header, rows } = parseCsvSimple(csv); 

  const lower = header.map(h => String(h || '').trim().toLowerCase());
  const idx = {
    ts:          lower.indexOf('timestamp'),
    height:      lower.indexOf('height'),
    hash:        lower.indexOf('block hash'),
    extraNonce:  lower.indexOf('extra nonce'),
    isOrphan:    lower.indexOf('is_orphan'),
    isQubic:     lower.indexOf('is_qubic'),
    difficulty:  lower.indexOf('difficulty'),
  };

  const orphanByH = new Map();
  const mainByH   = new Map();

  for (let i=0;i<rows.length;i++){
    const r = rows[i];
    const h = asInt(r[idx.height]);

    const rec = {
      height: h,
      hash: String(r[idx.hash] ?? ''),
      ts: asIsoTs(r[idx.ts]),
      extra_nonce: r[idx.extraNonce],
      is_qubic: normBoolTF(r[idx.isQubic]),
      difficulty: Number(String(r[idx.difficulty]).replace(/,/g, '')),
    };

    const is_orphan = normBoolTF(r[idx.isOrphan]);
    if (is_orphan) {
      if (!orphanByH.has(h)) orphanByH.set(h, rec);
    } else {
      if (!mainByH.has(h)) mainByH.set(h, rec);
    }
  }

  const orphanHeights = [...orphanByH.keys()].sort((a,b)=>a-b);
  const ranges = findConsecutiveRuns(orphanHeights, minRun);

  const runsAll = ranges.map(([s,e])=>{
    const orphan_blocks = [];
    for (let h=s; h<=e; h++){
      const o = orphanByH.get(h);
      if (o) orphan_blocks.push(o);
    }
    const mainchain_window = [];
    for (let h=s-1; h<=e+1; h++){
      const m = mainByH.get(h);
      if (m) mainchain_window.push(m);
    }
    return { start_height:s, end_height:e, orphan_blocks, mainchain_window };
  });

  const runs = runsAll.filter(r => isQubicSelfishRun(r.start_height, r.end_height, mainByH));

  res.json({
    meta: {
      BLOCKS_CSV_PATH,
      minRun,
      rowsSeen: rows.length,
      orphan_count: orphanHeights.length,
      main_count: mainByH.size,
      run_count_total: ranges.length,
      run_count_qubic: runs.length,
      ms: Date.now() - started
    },
    runs
  });
});

module.exports = router;
