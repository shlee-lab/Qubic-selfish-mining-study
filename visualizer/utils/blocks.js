// utils/blocks.js
function collapseByHashChange(header, rows) {
  if (!rows.length) return { header, rows: [] };
  let hashIdx = header.findIndex(h => h.trim().toLowerCase() === 'hash');
  if (hashIdx < 0) hashIdx = 3; // fallback (blocks.csv 0..3:hash)
  const out = [];
  let lastHash = null;
  for (const r of rows) {
    const h = (r[hashIdx] || '').trim();
    if (!h) continue;
    if (h !== lastHash) {
      out.push(r);
      lastHash = h;
    }
  }
  return { header, rows: out };
}

module.exports = { collapseByHashChange };

