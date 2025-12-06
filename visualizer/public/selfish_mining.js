(function () {
  const $ = (s, el=document) => el.querySelector(s);
  const tooltip = $("#tooltip");

  let ALL_RUNS = [];
  let LAST_META = null;

  // ---------- geometry ----------
  const BLOCK_W   = 120;
  const BLOCK_H   = 36;
  const GAP       = 10;
  const LEFT_PAD  = 135;
  const RIGHT_PAD = 10;
  const ARROW_PAD_RIGHT = 48; // ensure right arrow never clips
  const TOP_PAD   = 5;
  const TITLE_GAP = 20;
  const LANE_GAP  = 30;
  const BOTTOM_PAD= 20;
  const RX        = 10;

  // stroke widths (lane connectors, arrows, etc.)
  const LINE_W = 3;

  // ---------- explorer ----------
  const EXPLORER_BASE = 'https://blocks.p2pool.observer/block/';

  // ---------- colors ----------
  const css = (v)=>getComputedStyle(document.documentElement).getPropertyValue(v).trim();

  const STROKE_MAIN   = '#0f7a3a'; // deep green
  const STROKE_ORPHAN = '#c62828'; // deep red

  function fillColor(block, lane) {
    const isQ = block?.is_qubic === true;
    const isOrphan = lane === 'orphan' || block?.is_orphan === true;
    if (isQ) return css('--qubic');
    if (isOrphan) return css('--orphan');
    return css('--main');
  }

  // ---------- tooltip ----------
  const fmtH = h => (typeof h === 'number' ? `h=${h}` : `${h}`);
  function tipHtml(b, lane){
    const hh = b.hash ? String(b.hash) : '';
    return [
      `<div><b>${lane === 'main' ? 'Main' : 'Orphan'}</b> · <span class="kbd">${fmtH(b.height)}</span></div>`,
      hh ? `<div>hash: <span class="kbd" title="${hh}">${hh.slice(0,18)}${hh.length>18?'…':''}</span></div>` : '',
      b.ts ? `<div>time: <span class="kbd">${b.ts}</span></div>` : ''
    ].filter(Boolean).join('');
  }
  function showTip(e, html){
    tooltip.innerHTML = html;
    tooltip.style.opacity = 1;
    const pad = 10, vw = window.innerWidth, vh = window.innerHeight;
    tooltip.style.left = '-9999px'; tooltip.style.top  = '-9999px';
    requestAnimationFrame(() => {
      const rect = tooltip.getBoundingClientRect();
      const ttW = rect.width  || 260;
      const ttH = rect.height || 100;
      let x = e.clientX + pad, y = e.clientY + pad;
      if (x + ttW + pad > vw) x = Math.max(pad, vw - ttW - pad);
      if (y + ttH + pad > vh) y = Math.max(pad, e.clientY - ttH - pad);
      tooltip.style.left = x + 'px';
      tooltip.style.top  = y + 'px';
    });
  }
  function hideTip(){ tooltip.style.opacity = 0; }

  // ---------- date utils ----------
  function toDateStr(ts){
    if (!ts) return null; const d=new Date(ts); if (isNaN(d)) return null;
    const y=d.getFullYear(), m=String(d.getMonth()+1).padStart(2,'0'), day=String(d.getDate()).padStart(2,'0');
    return `${y}-${m}-${day}`;
  }
  function tsInRangeUTC(ts, ymdStart, ymdEnd){
    if (!ts) return false;
    const d = new Date(ts); if (isNaN(d)) return false;
    const s = ymdStart ? new Date(ymdStart + 'T00:00:00Z') : null;
    const e = ymdEnd   ? new Date(ymdEnd   + 'T23:59:59.999Z') : null;
    const t = d.getTime();
    if (s && t < s.getTime()) return false;
    if (e && t > e.getTime()) return false;
    return true;
  }

  // ---------- render ----------
  function render(runs){
    const container = $("#container");
    container.innerHTML = '';
    if (!runs || runs.length===0){
      const div = document.createElement('div'); div.className='empty card'; div.textContent='No runs to display.'; container.appendChild(div); return;
    }
    for (const run of runs) container.appendChild(renderRun(run));
  }

  function renderRun(run){
    const HMIN = Math.min(run.start_height-1, ...run.orphan_blocks.map(b=>b.height));
    const HMAX = Math.max(run.end_height+1,   ...run.orphan_blocks.map(b=>b.height));
    const MC_MIN = Math.min(...run.mainchain_window.map(b=>b.height), run.start_height-1);
    const MC_MAX = Math.max(...run.mainchain_window.map(b=>b.height), run.end_height+1);
    const minH = Math.min(HMIN, MC_MIN);
    const maxH = Math.max(HMAX, MC_MAX);
    const cols = maxH - minH + 1;

    const card = div('card');
    const firstTs = run.orphan_blocks?.[0]?.ts || run.mainchain_window?.[0]?.ts || '';
    const dstr = toDateStr(firstTs) || '-';
    const length = (run.end_height - run.start_height + 1);
    const title = div('row-title');
    title.style.justifyContent = 'flex-start';
    title.innerHTML =
      `<span class="hl">${run.start_height}~${run.end_height}</span>
       <span class="meta">(length ${length})  date: ${dstr}</span>`;
    card.appendChild(title);

    const tp = TOP_PAD + TITLE_GAP;

    const colW = BLOCK_W + GAP;
    const innerW = cols*colW - GAP;
    const svgW = LEFT_PAD + innerW + RIGHT_PAD + ARROW_PAD_RIGHT;
    const svgH = tp + (BLOCK_H*2) + LANE_GAP + BOTTOM_PAD;

    const wrap = div('canvas');
    const svg  = sEl('svg', { width: svgW, height: svgH });
    wrap.appendChild(svg);
    card.appendChild(wrap);

    // column grid + height labels
    for (let h=minH; h<=maxH; h++){
      const i = h - minH;
      const x = LEFT_PAD + i*colW + BLOCK_W/2;
      const t = sEl('text', { x, y: tp - 12 });
      t.textContent = String(h);
      t.setAttribute('text-anchor','middle');
      t.setAttribute('class', 'axes');
      svg.appendChild(t);
      svg.appendChild(sEl('line', { x1:x, y1:tp-6, x2:x, y2:svgH-8, stroke:css('--grid'), 'stroke-width':1 }));
    }

    const rs = run.start_height - minH;
    const re = run.end_height - minH;
    const bandX = LEFT_PAD + rs*colW - Math.max(4, GAP/2);
    const bandW = (re - rs + 1)*colW - GAP + Math.max(8, GAP);
    svg.appendChild(sEl('rect', { x:bandX, y:tp, width:bandW, height:(BLOCK_H*2 + LANE_GAP + 18), fill: css('--runbg') }));

    const mainCY   = tp + BLOCK_H/2;
    const orphanCY = tp + BLOCK_H + LANE_GAP + BLOCK_H/2;

    // --- lane labels (bold; Orphan red) ---
    const mainLbl = textEl(14, mainCY, 'Mainchain', 'lane-label');
    mainLbl.setAttribute('dominant-baseline','middle');
    mainLbl.setAttribute('font-weight','700');
    svg.appendChild(mainLbl);

    const orLbl = textEl(14, orphanCY + 4, 'Orphan', 'lane-label');
    orLbl.setAttribute('font-weight','700');
    orLbl.setAttribute('fill', STROKE_ORPHAN);
    svg.appendChild(orLbl);

    const mcByH = new Map(run.mainchain_window.map(b=>[b.height,b]));
    const orByH = new Map(run.orphan_blocks.map(b=>[b.height,b]));

    // connections: use deep green / deep red
    drawLaneConnections(svg, mcByH, minH, maxH, mainCY,   STROKE_MAIN);
    drawLaneConnections(svg, orByH, minH, maxH, orphanCY, STROKE_ORPHAN);

    drawForkElbowDownThenRight(svg, tp, minH, run.start_height, mcByH, orByH, orphanCY);
    drawMainchainContinuationHints(svg, mcByH, minH, maxH, mainCY);

    const shortLabel8 = (hash) => {
      if (!hash) return '';
      const h = String(hash).replace(/^0x/i, '');
      return '0x' + h.slice(0, 8);  // 4 bytes = 8 hex
    };
    const openExplorer = (hash) => { if (hash) window.open(EXPLORER_BASE + String(hash), '_blank', 'noopener'); };

    // main blocks
    for (let h=minH; h<=maxH; h++){
      const b = mcByH.get(h); if (!b) continue;
      const x = LEFT_PAD + (h-minH)*colW;
      const y = tp;
      const rect = sEl('rect', {
        x, y, width:BLOCK_W, height:BLOCK_H, rx:RX, ry:RX,
        class: 'block',
        fill: fillColor({ ...b, is_orphan:false }, 'main'),
        stroke: 'rgba(0,0,0,0.18)', 'stroke-width': 1
      });
      svg.appendChild(rect);

      const tx = x + BLOCK_W/2;
      const ty = y + BLOCK_H/2 + 0.5;
      const t = sEl('text', { x: tx, y: ty });
      t.setAttribute('text-anchor', 'middle');
      t.setAttribute('dominant-baseline', 'middle');
      t.setAttribute('font-size', '12');
      t.setAttribute('font-weight', '700');  
      t.setAttribute('fill', '#114353');    
      t.textContent = shortLabel8(b.hash);
      svg.appendChild(t);

      const go = () => openExplorer(b.hash);
      rect.addEventListener('click', go);
      t.addEventListener('click', go);

      const show = (e)=>showTip(e, tipHtml({ ...b, is_orphan:false }, 'main'));
      rect.addEventListener('mousemove', show);
      rect.addEventListener('mouseleave', hideTip);
      t.addEventListener('mousemove', show);
      t.addEventListener('mouseleave', hideTip);
    }

    // orphan blocks
    for (let h=minH; h<=maxH; h++){
      const b = orByH.get(h); if (!b) continue;
      const x = LEFT_PAD + (h-minH)*colW;
      const y = tp + BLOCK_H + LANE_GAP;
      const rect = sEl('rect', {
        x, y, width:BLOCK_W, height:BLOCK_H, rx:RX, ry:RX,
        class: 'block',
        fill: fillColor({ ...b, is_orphan:true }, 'orphan'),
        stroke: 'rgba(0,0,0,0.18)', 'stroke-width': 1
      });
      svg.appendChild(rect);

      const tx = x + BLOCK_W/2;
      const ty = y + BLOCK_H/2 + 0.5;
      const t = sEl('text', { x: tx, y: ty });
      t.setAttribute('text-anchor', 'middle');
      t.setAttribute('dominant-baseline', 'middle');
      t.setAttribute('font-size', '12');
      t.setAttribute('font-weight', '700');  
      t.setAttribute('fill', '#6c3635');     
      t.textContent = shortLabel8(b.hash);
      svg.appendChild(t);

      const go = () => openExplorer(b.hash);
      rect.addEventListener('click', go);
      t.addEventListener('click', go);

      const show = (e)=>showTip(e, tipHtml({ ...b, is_orphan:true }, 'orphan'));
      rect.addEventListener('mousemove', show);
      rect.addEventListener('mouseleave', hideTip);
      t.addEventListener('mousemove', show);
      t.addEventListener('mouseleave', hideTip);
    }

    card.appendChild(div('sep'));
    return card;
  }

  // lane polylines
  function drawLaneConnections(svg, mapByH, minH, maxH, yCenter, stroke){
    const colW = BLOCK_W + GAP;
    let seg = [];
    for (let h=minH; h<=maxH; h++){
      if (!mapByH.has(h)){
        if (seg.length >= 2) addPath(seg);
        seg=[]; continue;
      }
      const x = LEFT_PAD + (h - minH)*colW + BLOCK_W/2;
      seg.push([x, yCenter]);
    }
    if (seg.length >= 2) addPath(seg);

    function addPath(points){
      const d = points.map((p,i)=> (i? 'L':'M') + p[0] + ' ' + p[1]).join(' ');
      svg.appendChild(sEl('path', { d, fill:'none', stroke, 'stroke-width': LINE_W, 'stroke-linecap':'round', 'stroke-linejoin':'round', opacity: 0.6 }));
    }
  }

  function drawForkElbowDownThenRight(svg, tp, minH, orphanStartH, mcByH, orByH, orphanCY){
    const colW = BLOCK_W + GAP;
    const main0H = minH;
    const m0  = mcByH.get(main0H);
    const oSt = orByH.get(orphanStartH);
    if (!m0 || !oSt) return;

    const x1 = LEFT_PAD + (main0H - minH)*colW + BLOCK_W/2;
    const y1 = tp + BLOCK_H;
    const x2 = LEFT_PAD + (orphanStartH - minH)*colW;
    const y2 = orphanCY;

    const d = `M ${x1} ${y1} L ${x1} ${y2} L ${x2} ${y2}`;
    svg.appendChild(sEl('path', {
      d, fill:'none', stroke: STROKE_ORPHAN, 'stroke-width': LINE_W, 'stroke-linecap': 'round', opacity: 0.95
    }));
  }

  function drawMainchainContinuationHints(svg, mcByH, minH, maxH, mainCY){
    const colW = BLOCK_W + GAP;

    let firstH = null, lastH = null;
    for (let h=minH; h<=maxH; h++){ if (mcByH.has(h)) { firstH = h; break; } }
    for (let h=maxH; h>=minH; h--){ if (mcByH.has(h)) { lastH = h; break; } }
    if (firstH == null || lastH == null) return;

    const firstXLeft = LEFT_PAD + (firstH - minH)*colW; 

    const DOT_R = LINE_W / 2; 
    const DOT_SP = 8;         
    const DOT_TO_LINE_GAP = 12;
    const PRELINE_LEN = 22;     

    const preLineStartX = firstXLeft - PRELINE_LEN;
    const preLine = sEl('line', {
      x1: preLineStartX,
      y1: mainCY,
      x2: firstXLeft,
      y2: mainCY,
      stroke: STROKE_MAIN,
      'stroke-width': LINE_W,
      'stroke-linecap': 'round',
      opacity: 0.95
    });
    svg.appendChild(preLine);

    const lastDotCenterX = preLineStartX - DOT_TO_LINE_GAP - DOT_R;
    const secondDotCenterX = lastDotCenterX - DOT_SP;
    const firstDotCenterX  = secondDotCenterX - DOT_SP;

    [firstDotCenterX, secondDotCenterX, lastDotCenterX].forEach(cx => {
      svg.appendChild(sEl('circle', { cx, cy: mainCY, r: DOT_R, fill: STROKE_MAIN, opacity: 0.95 }));
    });

    const defs = sEl('defs', {});
    const marker = sEl('marker', {
      id: 'arrowhead-main',
      markerWidth: 5,
      markerHeight: 4,
      refX: 4,
      refY: 2,
      orient: 'auto',
      markerUnits: 'strokeWidth'
    });
    marker.appendChild(sEl('path', { d: 'M 0 0 L 5 2 L 0 4 z', fill: STROKE_MAIN }));
    defs.appendChild(marker);
    svg.appendChild(defs);

    const lastXRight = LEFT_PAD + (lastH - minH)*colW + BLOCK_W;
    const arrowLen = 24;
    const arrow = sEl('line', {
      x1: lastXRight,
      y1: mainCY,
      x2: lastXRight + arrowLen,
      y2: mainCY,
      stroke: STROKE_MAIN,
      'stroke-width': LINE_W,
      'stroke-linecap': 'round',
      'marker-end': 'url(#arrowhead-main)'
    });
    svg.appendChild(arrow);
  }

  // ---------- DOM helpers ----------
  const div = (cls)=>{ const e=document.createElement('div'); if (cls) e.className=cls; return e; };
  const sEl = (tag, attrs)=>{ const e=document.createElementNS('http://www.w3.org/2000/svg', tag); for (const k in attrs) e.setAttribute(k, attrs[k]); return e; };
  function textEl(x,y,txt,cls){ const t=sEl('text',{x,y}); if (cls) t.setAttribute('class',cls); t.textContent=txt; return t; }

  // ---------- filtering ----------
  const getRecent10 = (runs)=>[...runs].sort((a,b)=>(b.end_height||0)-(a.end_height||0)).slice(0,10);
  function filterByRange(runs, ymdStart, ymdEnd){
    if (!ymdStart && !ymdEnd) return [];
    return runs.filter(r => {
      const a = (r.orphan_blocks||[]).some(b => tsInRangeUTC(b.ts, ymdStart, ymdEnd));
      const m = (r.mainchain_window||[]).some(b => tsInRangeUTC(b.ts, ymdStart, ymdEnd));
      return a || m;
    });
  }

  // ---------- load ----------
  async function reload(){
    const minRun = Math.max(2, Number($("#minRun").value || 3));
    const url = `/api/selfish-mining?minRun=${encodeURIComponent(minRun)}`;
    const res = await fetch(url);
    if (!res.ok){ $("#container").innerHTML = `<div class="card empty">API error: ${res.status}</div>`; return; }
    const data = await res.json();
    LAST_META = data?.meta || null;
    ALL_RUNS = data?.runs || [];
    render(getRecent10(ALL_RUNS));
  }

  // ---------- events ----------
  $("#reload").addEventListener('click', reload);
  $("#showRecent").addEventListener('click', () => render(getRecent10(ALL_RUNS)));
  $("#applyRange").addEventListener('click', () => {
    const s = $("#dateStart").value?.trim();
    const e = $("#dateEnd").value?.trim() || s;
    if (!s && !e) { render(getRecent10(ALL_RUNS)); return; }
    render(filterByRange(ALL_RUNS, s || null, e || null));
  });

  window.addEventListener('load', reload);
})();

