/* All visible states and probabilities come from the recorded arena JSON. */
(() => {
  'use strict';
  const $ = (id) => document.getElementById(id);
  const ORDER = ['jev', 'nanojev', 'laya'];
  const ACCENTS = { jev: '#578d9a', nanojev: '#198875', laya: '#8b77b1' };
  const ENGINE_TITLES = {
    jev: { role: 'TYPE SAFE · CLOUD API', name: 'Jev' },
    nanojev: { role: '0.6B · LOCAL WEIGHTS', name: 'NanoJev' },
    laya: { role: '421M · LOCAL WEIGHTS', name: 'Laya' },
  };
  const DIRS = { 'up': '↑ Up', 'down': '↓ Down', 'left': '← Left', 'right': '→ Right' };
  const actionLabel = (game, action) => {
    if (action == null) return '—';
    if (game === '1024') return DIRS[action] || action;
    // tetris v2 combined action "r<orient>c<col>"
    const m = /^r(\d+)c(\d+)$/.exec(String(action));
    if (!m) return action;
    const rot = { 0: '0°', 1: '90°', 2: '180°', 3: '270°' }[m[1]] || `${m[1]}°`;
    return `${rot} @ col ${m[2]}`;
  };
  const state = { data: null, game: '1024', seed: null, step: 0, speed: 16, playing: false, animation: null, tick: 0, panels: [] };
  const api = { ready: false, error: null, setFrame, getSnapshot };
  window.jevArena = api;

  const examplesFor = () => state.data.examples.filter((e) => e.game === state.game);
  const seedsFor = () => [...new Set(examplesFor().map((e) => e.seed))];
  const currentRuns = () => examplesFor().filter((e) => e.seed === state.seed);
  const runFor = (engine) => currentRuns().find((e) => e.engine === engine);
  const lastStep = () => Math.max(...currentRuns().map((e) => e.frames.length - 1));
  const value = (v) => v == null ? '—' : String(v);
  // slim encoding stores rows as comma-joined cell strings ('.' = empty);
  // the full recording stores raw number grids. Decode to number[][] either way.
  const decodeGrid = (g) => (Array.isArray(g) && typeof g[0] === 'string')
    ? g.map((row) => row.split(',').map((v) => v === '.' ? 0 : Number(v)))
    : g;

  function validateData(data) {
    if (!data || !/^jev-arena-v[123]$/.test(data.schema || '') || !Array.isArray(data.examples) || !data.examples.length) {
      throw new Error('The recording file does not contain a supported arena dataset.');
    }
    for (const ex of data.examples) {
      if (!['tetris', '1024'].includes(ex.game) || !Array.isArray(ex.frames) || ex.frames.length < 1) {
        throw new Error('A recorded run has no frames.');
      }
      for (const fr of ex.frames) {
        if (fr.grid !== undefined && !Array.isArray(fr.grid)) throw new Error('A frame grid is malformed.');
        for (const p of Object.values(fr.probabilities || {})) {
          if (typeof p !== 'number' || !Number.isFinite(p) || p < 0 || p > 1) throw new Error('A recorded probability is invalid.');
        }
      }
    }
  }

  function pause() {
    state.playing = false;
    if (state.animation !== null) cancelAnimationFrame(state.animation);
    state.animation = null;
    $('playIcon').textContent = '▶';
    $('play').setAttribute('aria-label', 'Play all three recordings');
  }

  function getSnapshot() {
    if (!api.ready) return { ready: false, error: api.error };
    return JSON.parse(JSON.stringify({
      ready: true, error: null, game: state.game, seed: state.seed,
      step: state.step, totalSteps: lastStep(), playing: state.playing, stepsPerSecond: state.speed,
      runs: currentRuns().map((run) => {
        const local = Math.min(state.step, run.frames.length - 1);
        return { engine: run.engine, localStep: local, totalSteps: run.frames.length - 1,
          finished: local === run.frames.length - 1, frame: run.frames[local], summary: run.summary };
      }),
    }));
  }

  function setFrame(game, seed, step) {
    if (!api.ready) throw new Error(api.error || 'Recordings are still loading.');
    state.game = game; state.seed = seed; state.step = step;
    renderScene();
    renderFrame();
    return getSnapshot();
  }

  function outcomeLabel(run) {
    const s = run.summary || {};
    if (s.outcome === 'win') return 'Board cleared';
    if (s.outcome === 'engine_failure') return 'Engine error';
    if (s.outcome === 'stuck') return 'No moves left';
    if (s.outcome === 'topped out') return 'Topped out';
    if (s.outcome === 'horizon' || s.outcome === 'alive') return 'Alive at limit';
    return value(s.outcome);
  }
  const isPositive = (label) => ['Board cleared'].includes(label);

  function renderScene() {
    const example = currentRuns()[0];
    $('sceneTag').textContent = state.game.toUpperCase();
    $('sceneTitle').textContent = state.game === 'tetris' ? 'Clear lines, survive the stack' : 'Merge to 1024';
    $('sceneSize').textContent = state.game === 'tetris' ? '10 × 14 board' : '4 × 4 board';
    $('sceneCaption').textContent = state.game === 'tetris'
      ? 'One Choice question per piece: pick the drop column'
      : 'One Choice question per turn: pick the slide direction';
    document.querySelectorAll('[data-game]').forEach((button) => {
      const active = button.dataset.game === state.game;
      button.classList.toggle('active', active);
      button.setAttribute('aria-pressed', String(active));
    });
    state.panels = ORDER.map((engine) => {
      const run = runFor(engine);
      const card = $('modelTemplate').content.firstElementChild.cloneNode(true);
      card.dataset.engine = engine;
      card.style.setProperty('--accent', ACCENTS[engine]);
      card.classList.toggle('primary', engine === 'jev');
      card.querySelector('.model-role').textContent = ENGINE_TITLES[engine].role;
      card.querySelector('.model-name').textContent = ENGINE_TITLES[engine].name;
      card.querySelector('.model-name').title = run ? run.id : engine;
      card.querySelector('.stat-secondary-label').innerHTML =
        state.game === 'tetris' ? 'Lines <b>· holes</b>' : 'Max tile <b>· score</b>';
      const canvas = card.querySelector('canvas');
      canvas.setAttribute('aria-label', `${ENGINE_TITLES[engine].name}: ${state.game} recorded board`);
      // board aspect follows the game grid (tetris 10x20, 1024 4x4)
      canvas.style.aspectRatio = state.game === 'tetris' ? '10 / 20' : '1 / 1';
      const context = canvas.getContext('2d', { willReadFrequently: true });
      if (!context) throw new Error('This browser does not support a 2D game canvas.');
      const options = run && run.frames[1] ? Object.keys(run.frames[1].probabilities || {}) : [];
      const bars = options.map((opt) => {
        const item = document.createElement('div');
        item.className = 'probability-item';
        const top = document.createElement('div'); top.className = 'probability-top';
        const label = document.createElement('span'); label.textContent = actionLabel(state.game, opt);
        label.title = label.textContent;
        const val = document.createElement('span'); val.className = 'probability-value';
        top.append(label, val);
        const track = document.createElement('div'); track.className = 'probability-track';
        const fill = document.createElement('div'); fill.className = 'probability-fill'; track.append(fill);
        item.append(top, track);
        card.querySelector('.probability-grid').append(item);
        return { opt, item, val, fill };
      });
      return { engine, run, card, canvas, context, bars };
    });
    $('modelPanels').replaceChildren(...state.panels.map((p) => p.card));
    $('timeline').max = lastStep();
  }

  function renderFrame() {
    for (const panel of state.panels) {
      const { run, card } = panel;
      if (!run) continue;
      const step = Math.min(state.step, run.frames.length - 1);
      const frame = run.frames[step];
      const final = step === run.frames.length - 1;
      const label = final ? outcomeLabel(run) : step === 0 ? 'Ready' : 'Playing';
      card.querySelector('.stat-steps').textContent = step;
      card.querySelector('.stat-total').textContent = `/ ${run.frames.length - 1} recorded`;
      const m = frame.metrics || {};
      card.querySelector('.stat-secondary').textContent = state.game === 'tetris'
        ? `${value(m.lines)} · ${value(m.holes)}` : `${value(m.max_tile)} · ${value(m.score)}`;
      card.querySelector('.stat-status').textContent = label;
      card.querySelector('.stat-status').style.color = isPositive(label) ? '#17694f'
        : ['Topped out', 'No moves left', 'Engine error'].includes(label) ? '#a34d33' : 'inherit';
      card.querySelector('.stat-outcome').textContent = final ? 'Final frame held'
        : state.game === 'tetris' ? `height ${value(m.max_height)}` : `${value(m.score)} pts`;
      const badge = card.querySelector('.board-status');
      badge.hidden = !final;
      badge.textContent = (isPositive(label) ? '✓ ' : '') + label;
      badge.classList.toggle('negative', !isPositive(label));
      const isDecision = step > 0 && frame.action != null;
      card.querySelector('.decision-title').textContent = step ? 'Last decision' : 'Initial state';
      card.querySelector('.decision-action').textContent = !step ? 'No action yet'
        : `${actionLabel(state.game, frame.action)}${frame.violation ? ' · off-board' : ''}`;
      card.querySelector('.decision-action').style.color = frame.violation ? '#a34d33' : '';
      for (const bar of panel.bars) {
        const v = step ? (frame.probabilities || {})[bar.opt] : undefined;
        bar.val.textContent = v === undefined ? '—' : `${(v * 100).toFixed(1)}%`;
        bar.fill.style.width = `${v === undefined ? 0 : v * 100}%`;
        bar.item.classList.toggle('chosen', step > 0 && frame.action === bar.opt);
      }
      card.querySelector('.probability-kind').textContent = !step ? 'Awaiting the first recorded action'
        : frame.violation ? 'Chosen option was not legal — engine override'
        : frame.decision_source === 'forced' ? 'Single legal action · executed by code'
        : frame.noul != null ? `Action probabilities · noul gate ${frame.noul.toFixed(2)}`
        : frame.confidence != null ? `Action probabilities · confidence ${(frame.confidence * 100).toFixed(0)}%`
        : 'Action probabilities';
      card.querySelector('.decision-origin').textContent = step
        ? (frame.latency_ms != null ? `${frame.latency_ms} ms decision` : '') : '';
      drawBoard(panel, step);
    }
    const end = lastStep();
    $('timeline').value = state.step;
    $('timeline').style.setProperty('--progress', `${end ? (state.step / end) * 100 : 0}%`);
    $('stepCounter').textContent = `${state.step} / ${end}`;
    $('previous').disabled = state.step === 0; $('restart').disabled = state.step === 0;
    $('next').disabled = state.step === end; $('play').disabled = end === 0;
  }

  function drawBoard(panel, step) {
    const { canvas, context: ctx, run } = panel;
    if (!run) return;
    const rect = canvas.getBoundingClientRect();
    if (rect.width < 1 || rect.height < 1) return;
    const ratio = Math.min(window.devicePixelRatio || 1, 2);
    if (canvas.width !== Math.round(rect.width * ratio) || canvas.height !== Math.round(rect.height * ratio)) {
      canvas.width = Math.round(rect.width * ratio); canvas.height = Math.round(rect.height * ratio);
    }
    ctx.save();
    ctx.setTransform(ratio, 0, 0, ratio, 0, 0);
    ctx.clearRect(0, 0, rect.width, rect.height);
    const frame = run.frames[step];
    if (!frame || frame.grid === undefined) { ctx.restore(); return; }
    const accent = ACCENTS[panel.engine];
    const grid = decodeGrid(frame.grid);
    const rows = grid.length, cols = grid[0].length;
    const margin = 8;
    const cell = Math.min((rect.width - margin * 2) / cols, (rect.height - margin * 2) / rows);
    const sideW = cell * cols, sideH = cell * rows;
    const left = (rect.width - sideW) / 2, top = (rect.height - sideH) / 2;
    const center = ([r, c]) => [left + (c + .5) * cell, top + (r + .5) * cell];
    const round = (x, y, w, h, radius) => {
      ctx.beginPath(); ctx.roundRect(x, y, w, h, Math.min(radius, w / 2, h / 2)); ctx.fill();
    };

    if (state.game === 'tetris') {
      ctx.fillStyle = '#f2f5ef'; ctx.fillRect(left, top, sideW, sideH);
      ctx.strokeStyle = '#e6ece1'; ctx.lineWidth = .6; ctx.beginPath();
      for (let n = 1; n < cols; n++) { ctx.moveTo(left + n * cell, top); ctx.lineTo(left + n * cell, top + sideH); }
      for (let n = 1; n < rows; n++) { ctx.moveTo(left, top + n * cell); ctx.lineTo(left + sideW, top + n * cell); }
      ctx.stroke();
      const colors = { 1: '#9fc3ad', 2: '#7aa4b0', 3: '#c9b3d9', 4: '#e8c8a0', 5: '#d9a38c' };
      for (let r = 0; r < rows; r++) for (let c = 0; c < cols; c++) {
        const v = grid[r][c];
        if (!v) continue;
        ctx.fillStyle = colors[v] || accent;
        round(left + c * cell + 1, top + r * cell + 1, cell - 2, cell - 2, Math.max(1.5, cell * .14));
      }
      // highlight the latest piece cells (cells of the chosen color in the newest rows)
      if (step > 0) {
        const prev = run.frames[step - 1].grid;
        for (let r = 0; r < rows; r++) for (let c = 0; c < cols; c++) {
          if (grid[r][c] && grid[r][c] !== prev[r][c]) {
            ctx.strokeStyle = accent; ctx.lineWidth = 1.4;
            ctx.strokeRect(left + c * cell + 1.5, top + r * cell + 1.5, cell - 3, cell - 3);
          }
        }
      }
      ctx.strokeStyle = '#d7e1d2'; ctx.lineWidth = .8; ctx.strokeRect(left, top, sideW, sideH);
    } else {
      ctx.fillStyle = '#fbfcf9'; ctx.fillRect(left, top, sideW, sideH);
      // trail: alpha ghosts of previous positions of the max tile
      if (step > 1) {
        const prevMax = run.frames[step - 1].metrics.max_tile;
        for (let s = Math.max(0, step - 6); s < step; s++) {
          const g = run.frames[s].grid;
          for (let r = 0; r < rows; r++) for (let c = 0; c < cols; c++) {
            if (g[r][c] === prevMax && prevMax >= 128) {
              ctx.fillStyle = `${accent}14`;
              round(left + c * cell + 1, top + r * cell + 1, cell - 2, cell - 2, cell * .12);
            }
          }
        }
      }
      const tileStyle = (v) => {
        if (!v) return { bg: 'transparent', fg: 'transparent', size: .5 };
        const tiers = {
          2: ['#eef2ea', '#5c6d64', .42], 4: ['#e3eae0', '#4c5c54', .42],
          8: ['#d4e6d3', '#33544a', .44], 16: ['#b9d8c4', '#2d4f42', .44],
          32: ['#96c7ae', '#ffffff', .46], 64: ['#78b397', '#ffffff', .46],
          128: ['#578d9a', '#ffffff', .42], 256: ['#4d8394', '#ffffff', .42],
          512: ['#198875', '#ffffff', .42], 1024: ['#17694f', '#ffffff', .40],
          2048: ['#df816c', '#ffffff', .40],
        };
        const t = tiers[v] || ['#df816c', '#ffffff', .38];
        return { bg: t[0], fg: t[1], size: t[2] };
      };
      for (let r = 0; r < rows; r++) for (let c = 0; c < cols; c++) {
        const v = grid[r][c];
        const x = left + c * cell, y = top + r * cell;
        if (!v) {
          ctx.fillStyle = '#eef2ea';
          round(x + 1, y + 1, cell - 2, cell - 2, cell * .12);
          continue;
        }
        const style = tileStyle(v);
        const isMax = v === (frame.metrics.max_tile || 0);
        if (isMax) { ctx.shadowColor = `${accent}55`; ctx.shadowBlur = 9; }
        ctx.fillStyle = style.bg;
        round(x + 1, y + 1, cell - 2, cell - 2, cell * .12);
        ctx.shadowBlur = 0;
        if (v) {
          ctx.fillStyle = style.fg;
          ctx.font = `650 ${Math.max(9, cell * style.size)}px Inter, sans-serif`;
          ctx.textAlign = 'center'; ctx.textBaseline = 'middle';
          ctx.fillText(String(v), x + cell / 2, y + cell / 2 + cell * .03);
        }
      }
      // spawn marker on the newest tile
      if (step > 0) {
        const prev = run.frames[step - 1].grid;
        for (let r = 0; r < rows; r++) for (let c = 0; c < cols; c++) {
          if (grid[r][c] && !prev[r][c]) {
            ctx.strokeStyle = '#df816c'; ctx.lineWidth = 1.4;
            ctx.strokeRect(left + c * cell + 1.5, top + r * cell + 1.5, cell - 3, cell - 3);
          }
        }
      }
      ctx.strokeStyle = '#d7e1d2'; ctx.lineWidth = .8; ctx.strokeRect(left, top, sideW, sideH);
    }
    ctx.restore();
  }

  function play() {
    if (!api.ready || lastStep() === 0) return;
    if (state.playing) { pause(); return; }
    if (state.step === lastStep()) { state.step = 0; renderFrame(); }
    state.playing = true; state.tick = performance.now();
    $('playIcon').textContent = 'Ⅱ';
    $('play').setAttribute('aria-label', 'Pause all three recordings');
    function advance(now) {
      if (!state.playing) return;
      const interval = 1000 / state.speed;
      const count = Math.floor((now - state.tick) / interval);
      if (count > 0) {
        state.tick += count * interval;
        state.step = Math.min(lastStep(), state.step + count);
        renderFrame();
        if (state.step === lastStep()) { pause(); return; }
      }
      state.animation = requestAnimationFrame(advance);
    }
    state.animation = requestAnimationFrame(advance);
  }

  function renderTallies() {
    const tally = state.data.tallies || {};
    const wrap = $('tallyTables');
    wrap.replaceChildren();
    for (const game of Object.keys(tally)) {
      const title = document.createElement('h3');
      title.textContent = game === 'tetris' ? 'Tetris' : '1024';
      const table = document.createElement('table');
      table.className = 'match-table';
      const cols = game === 'tetris'
        ? ['Engine', 'Score', 'Lines', 'Pieces', 'Holes', 'Orients used', 'Off-board picks', 'Avg decision']
        : ['Engine', 'Score', 'Max tile', 'Oscillation', 'Repeats', 'Result', 'Off-board picks', 'Avg decision'];
      const thead = document.createElement('thead');
      const trh = document.createElement('tr');
      for (const c of cols) { const th = document.createElement('th'); th.textContent = c; trh.append(th); }
      thead.append(trh); table.append(thead);
      const tbody = document.createElement('tbody');
      // winner = highest avg score
      const rows = tally[game];
      const best = Math.max(...rows.map((r) => r.score || 0));
      for (const r of rows) {
        const tr = document.createElement('tr');
        if (r.score === best && best > 0) tr.className = 'winner';
        const td = (v, cls) => { const d = document.createElement('td'); if (cls) d.className = cls; d.textContent = value(v); return d; };
        const chip = document.createElement('td');
        chip.innerHTML = `<span class="engine-chip"><i style="background:${ACCENTS[r.engine]}"></i>${ENGINE_TITLES[r.engine]?.name || r.engine}</span>`;
        tr.append(chip);
        if (game === 'tetris') {
          const orientCell = td(r.orientations_used != null ? `${r.orientations_used} / ${r.pieces ? '≥2' : '—'}` : '—', 'num');
          orientCell.title = r.orientation_usage ? JSON.stringify(r.orientation_usage) : '';
          tr.append(td(r.score, 'num'), td(r.lines, 'num'), td(r.pieces, 'num'), td(r.holes, 'num'),
            orientCell, td(r.violations, 'num'), td(r.avg_latency_ms ? `${Math.round(r.avg_latency_ms)} ms` : '—', 'num'));
        } else {
          const oscCell = td(r.oscillation_rate != null ? `${(r.oscillation_rate * 100).toFixed(0)}%` : '—', 'num');
          oscCell.title = r.direction_usage ? JSON.stringify(r.direction_usage) : '';
          tr.append(td(r.score, 'num'), td(r.max_tile, 'num'), oscCell,
            td(r.repeat_rate != null ? `${(r.repeat_rate * 100).toFixed(0)}%` : '—', 'num'),
            td(r.outcome), td(r.violations, 'num'), td(r.avg_latency_ms ? `${Math.round(r.avg_latency_ms)} ms` : '—', 'num'));
        }
        tbody.append(tr);
      }
      table.append(tbody);
      const section = document.createElement('div');
      section.append(title, table);
      wrap.append(section);
    }
    $('tallyNote').textContent = `· seeds ${state.data.seeds?.join(' & ')} · ${state.data.generated || ''}`;
    $('aggregate').hidden = false;
  }

  function renderSeedSelect() {
    const sel = $('seedSelect');
    sel.replaceChildren(...seedsFor().map((seed) => {
      const opt = document.createElement('option');
      opt.value = seed; opt.textContent = seed; opt.selected = seed === state.seed;
      return opt;
    }));
  }

  function selectGame(game) {
    state.game = game;
    state.seed = seedsFor()[0];
    state.step = 0;
    renderSeedSelect();
    renderScene();
    renderFrame();
  }

  function selectHash() {
    if (!api.ready) return;
    const game = location.hash.toLowerCase() === '#tetris' ? 'tetris' : '1024';
    if (game !== state.game) selectGame(game); else { renderScene(); renderFrame(); }
  }
  document.querySelectorAll('[data-game]').forEach((button) => button.addEventListener('click', () => {
    if (!api.ready) return;
    if (location.hash === `#${button.dataset.game}`) selectHash(); else location.hash = button.dataset.game;
  }));
  window.addEventListener('hashchange', selectHash);
  $('seedSelect').addEventListener('change', (e) => { state.seed = Number(e.target.value); state.step = 0; renderScene(); renderFrame(); });
  $('play').addEventListener('click', play);
  $('restart').addEventListener('click', () => { state.step = 0; renderFrame(); });
  $('previous').addEventListener('click', () => { state.step = Math.max(0, state.step - 1); renderFrame(); });
  $('next').addEventListener('click', () => { state.step = Math.min(lastStep(), state.step + 1); renderFrame(); });
  $('timeline').addEventListener('input', (event) => { state.step = Number(event.target.value); renderFrame(); });
  $('speed').addEventListener('change', (event) => { state.speed = Number(event.target.value); state.tick = performance.now(); });
  new ResizeObserver(() => { if (api.ready) state.panels.forEach((p) => drawBoard(p, Math.min(state.step, (p.run?.frames.length || 1) - 1))); }).observe($('modelPanels'));
  document.addEventListener('visibilitychange', () => { if (document.hidden) pause(); });

  async function init() {
    try {
      let response = await fetch('./arena_slim.json', { cache: 'no-store' });
      if (!response.ok) {
        response = await fetch('./arena_results.json', { cache: 'no-store' });
      }
      if (!response.ok) throw new Error(`The recording file could not be loaded (HTTP ${response.status}).`);
      state.data = await response.json();
      validateData(state.data);
      state.game = location.hash.toLowerCase() === '#tetris' ? 'tetris' : '1024';
      state.seed = seedsFor()[0];
      $('loadState').hidden = true;
      $('viewer').hidden = false;
      renderSeedSelect();
      renderScene();
      api.ready = true;
      renderFrame();
      renderTallies();
    } catch (error) {
      pause(); api.ready = false; api.error = error.message;
      $('viewer').hidden = true;
      $('loadState').hidden = false;
      $('loadState').classList.add('error');
      $('loadState').querySelector('h2').textContent = 'The recordings are not available yet';
      $('loadState').querySelector('p').textContent = `${error.message} Serve this page alongside its arena_results.json file to view the real comparisons.`;
    }
  }
  init();
})();
