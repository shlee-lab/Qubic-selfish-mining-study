// config/paths.js — Qubic-Monero-Selfish-Mining-Analysis (visualizer + data)
const path = require('path');
const fs = require('fs');

function exists(p) {
  try { return !!p && fs.existsSync(p); } catch { return false; }
}
function firstExisting(paths) {
  for (const p of paths) if (exists(p)) return p;
  return null;
}


// __dirname is .../visualizer/config
const ROOT_DIR = __dirname.includes(path.sep + 'config')
  ? path.resolve(__dirname, '..')            // .../visualizer
  : path.resolve(__dirname);

const PARENT_DIR = path.resolve(ROOT_DIR, '..'); 



// ----- PUBLIC (static + HTML) -----
// Priority: ENV → <visualizer>/public → <visualizer>
const PUBLIC_DIR = firstExisting([
  process.env.PUBLIC_DIR,
  path.resolve(ROOT_DIR, 'public'),
  ROOT_DIR,
]) || path.resolve(ROOT_DIR, 'public');

// HTML entry points (served via res.sendFile)
const MAIN_HTML   = firstExisting([
  path.join(PUBLIC_DIR, 'main.html'),
]);
const JOBS_HTML   = firstExisting([
  path.join(PUBLIC_DIR, 'jobs.html'),
]);
const BLOCKS_HTML = firstExisting([
  path.join(PUBLIC_DIR, 'blocks.html'),
]);

// Also expose individual analysis pages located in /public
const COUNT_QUBIC_HTML  = firstExisting([
  path.join(PUBLIC_DIR, 'count_qubic.html'),
]);
const COUNT_ORPHAN_HTML = firstExisting([
  path.join(PUBLIC_DIR, 'count_orphan.html'),
]);

// ----- DATA dir & CSV files -----
// Priority: ENV → <project_root>/data → <visualizer>/data (fallback)
const DATA_DIR = firstExisting([
  process.env.DATA_DIR,
  path.resolve(PARENT_DIR, 'data'),
  path.resolve(ROOT_DIR, 'data'),
]);

const BLOCKS_CSV_PATH = firstExisting([
  process.env.BLOCKS_CSV_PATH,
  DATA_DIR && path.join(DATA_DIR, 'all_blocks.csv'),
]);

const JOBS_CSV_PATH = firstExisting([
  process.env.JOBS_CSV_PATH,
  DATA_DIR && path.join(DATA_DIR, 'jobs.csv'),
]);

const RAW_JOBS_CSV_PATH = firstExisting([
  process.env.RAW_JOBS_CSV_PATH,
  DATA_DIR && path.join(DATA_DIR, 'raw_jobs.csv'),
]);


// Helpful boot logger
function logResolvedPaths() {
  const dump = {
    // dirs
    ROOT_DIR,
    PARENT_DIR,
    DATA_DIR,
    PUBLIC_DIR,
    // html
    MAIN_HTML,
    JOBS_HTML,
    BLOCKS_HTML,
    COUNT_QUBIC_HTML,
    COUNT_ORPHAN_HTML,
    // csv
    BLOCKS_CSV_PATH,
    JOBS_CSV_PATH,
    RAW_JOBS_CSV_PATH,
  };
  try {
    console.log('[paths] resolved:\n' + JSON.stringify(dump, null, 2));
  } catch {
    console.log('[paths] resolved (no JSON)');
    console.log(dump);
  }
}

module.exports = {
  // base dirs
  ROOT_DIR,
  PARENT_DIR,
  DATA_DIR,
  PUBLIC_DIR,
  // html
  MAIN_HTML,
  JOBS_HTML,
  BLOCKS_HTML,
  COUNT_QUBIC_HTML,
  COUNT_ORPHAN_HTML,
  // csv
  BLOCKS_CSV_PATH,
  JOBS_CSV_PATH,
  RAW_JOBS_CSV_PATH,
  // utils
  logResolvedPaths,
};
