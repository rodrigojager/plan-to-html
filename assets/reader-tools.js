/* Content-independent reader controls. Themes never change these selectors. */
(() => {
  'use strict';
  const $ = selector => document.querySelector(selector);
  const $$ = selector => [...document.querySelectorAll(selector)];
  const root = document.documentElement;
  const labels = JSON.parse($('#plan-data').textContent).labels;
  let highlightTimer, highlighted, toastTimer;
  function highlight(target) {
    highlighted?.classList.remove('target-highlight');
    highlighted = target.matches('.source-title,.document')
      ? target.closest('.document').querySelector('.document-header')
      : target.matches('.hero') ? target.querySelector('h1') : target;
    highlighted.classList.add('target-highlight');
    clearTimeout(highlightTimer);
    highlightTimer = setTimeout(() => highlighted?.classList.remove('target-highlight'), 1600);
  }
  window.PlanHTMLTools = {highlight};

  async function copy(text, button) {
    try { await navigator.clipboard.writeText(text); }
    catch {
      const field = document.createElement('textarea');
      field.value = text; field.style.cssText = 'position:fixed;opacity:0';
      document.body.append(field); field.select(); document.execCommand('copy'); field.remove(); button.focus();
    }
    const toast = $('#toast'); toast.textContent = labels.copied; toast.hidden = false;
    clearTimeout(toastTimer); toastTimer = setTimeout(() => { toast.hidden = true; }, 1800);
  }
  $$('.heading-anchor').forEach(button => button.addEventListener('click', () => {
    const url = new URL(location.href); url.hash = button.dataset.anchor;
    copy(url.href, button);
  }));
  $$('.code-wrap-toggle').forEach(button => button.addEventListener('click', () => {
    const active = button.closest('.code-block').classList.toggle('wrap-code');
    button.setAttribute('aria-pressed', String(active));
  }));
  $$('.code-lines-toggle').forEach(button => button.addEventListener('click', () => {
    const hidden = button.closest('.code-block').classList.toggle('hide-line-numbers');
    button.setAttribute('aria-pressed', String(!hidden));
  }));

  // Reading preferences affect CSS variables only; absent values follow viewport defaults.
  const settings = $('#reading-dialog');
  const size = $('#reading-size'), spacing = $('#reading-spacing'), width = $('#reading-width');
  function syncSettings() {
    const css = getComputedStyle(root);
    size.value = parseFloat(css.getPropertyValue('--reading-font-size'));
    spacing.value = parseFloat(css.getPropertyValue('--reading-line-height'));
    width.value = css.getPropertyValue('--reading-width').trim();
    $('#reading-size-value').value = size.value + ' px';
    $('#reading-spacing-value').value = Number(spacing.value).toFixed(2);
  }
  $('#reading-settings').addEventListener('click', () => { syncSettings(); settings.showModal(); });
  function applySettings() {
    const prefs = {size: Number(size.value), spacing: Number(spacing.value), width: width.value};
    root.style.setProperty('--reading-font-size', prefs.size + 'px');
    root.style.setProperty('--reading-line-height', String(prefs.spacing));
    root.style.setProperty('--reading-width', prefs.width);
    try { localStorage.setItem('planhtml:reading', JSON.stringify(prefs)); } catch { /* optional storage */ }
    syncSettings(); window.dispatchEvent(new Event('resize'));
  }
  [size, spacing, width].forEach(control => control.addEventListener('input', applySettings));
  $('#reading-reset').addEventListener('click', () => {
    ['--reading-font-size', '--reading-line-height', '--reading-width'].forEach(name => root.style.removeProperty(name));
    try { localStorage.removeItem('planhtml:reading'); } catch { /* optional storage */ }
    syncSettings(); window.dispatchEvent(new Event('resize'));
  });

  // One state per viewer. SVG geometry determines zoom and fit; no content interpretation.
  const states = new WeakMap();
  const dialog = $('#diagram-dialog');
  let expanded = null;
  function initDiagram(viewer) {
    const viewport = viewer.querySelector('.diagram-viewport');
    const canvas = viewer.querySelector('.mermaid');
    const svg = canvas.querySelector('svg');
    if (!svg) { viewer.classList.remove('diagram-interactive'); return; }
    let state = states.get(viewer);
    if (!state) {
      state = {viewer, viewport, canvas, x: 0, y: 0, scale: 1, fitScale: 1};
      states.set(viewer, state);
      state.paint = () => {
        canvas.style.transform = `translate(${state.x}px, ${state.y}px) scale(${state.scale})`;
        viewer.querySelector('.diagram-scale').value = Math.round(state.scale / state.fitScale * 100) + '%';
        viewport.dataset.zoom = String(state.scale / state.fitScale);
      };
      state.fit = () => {
        if (!viewport.clientWidth || !state.w) return;
        state.fitScale = Math.min((viewport.clientWidth - 32) / state.w, (viewport.clientHeight - 32) / state.h, 1);
        state.scale = Math.max(0.001, state.fitScale);
        state.x = (viewport.clientWidth - state.w * state.scale) / 2;
        state.y = (viewport.clientHeight - state.h * state.scale) / 2;
        state.paint();
      };
      state.zoom = (factor, cx = viewport.clientWidth / 2, cy = viewport.clientHeight / 2) => {
        const scale = Math.max(state.fitScale / 4, Math.min(state.fitScale * 8, state.scale * factor));
        state.x = cx - (cx - state.x) * scale / state.scale;
        state.y = cy - (cy - state.y) * scale / state.scale;
        state.scale = scale; state.paint();
      };
      viewer.querySelectorAll('[data-diagram-action]').forEach(button => button.addEventListener('click', () => {
        const action = button.dataset.diagramAction;
        if (action === 'in') state.zoom(1.25);
        if (action === 'out') state.zoom(0.8);
        if (action === 'fit') state.fit();
        if (action === 'expand') {
          if (expanded) return;
          const wrap = viewer.closest('.diagram-wrap');
          const placeholder = document.createComment('diagram position');
          wrap.before(placeholder);
          expanded = {state, wrap, placeholder, button};
          $('#diagram-stage').append(wrap); dialog.showModal(); state.fit(); viewport.focus();
        }
      }));
      let drag = null;
      viewport.addEventListener('pointerdown', event => {
        if (event.button !== 0 || event.target.closest('a')) return;
        drag = {id: event.pointerId, x: event.clientX, y: event.clientY, sx: state.x, sy: state.y};
        viewport.setPointerCapture(event.pointerId); viewport.classList.add('panning'); viewport.focus({preventScroll: true});
        event.preventDefault();
      });
      viewport.addEventListener('pointermove', event => {
        if (!drag || event.pointerId !== drag.id) return;
        state.x = drag.sx + event.clientX - drag.x; state.y = drag.sy + event.clientY - drag.y; state.paint();
      });
      const stopDrag = () => { drag = null; viewport.classList.remove('panning'); };
      viewport.addEventListener('pointerup', stopDrag); viewport.addEventListener('pointercancel', stopDrag);
      viewport.addEventListener('lostpointercapture', stopDrag);
      viewport.addEventListener('keydown', event => {
        const moves = {ArrowLeft: [35, 0], ArrowRight: [-35, 0], ArrowUp: [0, 35], ArrowDown: [0, -35]};
        if (moves[event.key]) { const [x, y] = moves[event.key]; state.x += x; state.y += y; state.paint(); }
        else if (['+', '='].includes(event.key)) state.zoom(1.25);
        else if (event.key === '-') state.zoom(0.8);
        else if (['0', 'Home'].includes(event.key)) state.fit();
        else return;
        event.preventDefault();
      });
      viewport.addEventListener('wheel', event => {
        if (!event.ctrlKey && !event.metaKey) return;
        event.preventDefault(); const bounds = viewport.getBoundingClientRect();
        state.zoom(event.deltaY < 0 ? 1.1 : 1 / 1.1, event.clientX - bounds.left, event.clientY - bounds.top);
      }, {passive: false});
      new ResizeObserver(() => state.fit()).observe(viewport);
    }
    const box = svg.viewBox.baseVal;
    state.w = box.width || parseFloat(svg.getAttribute('width')) || 600;
    state.h = box.height || parseFloat(svg.getAttribute('height')) || 300;
    canvas.style.width = state.w + 'px'; canvas.style.height = state.h + 'px';
    svg.style.width = state.w + 'px'; svg.style.height = state.h + 'px';
    viewport.style.setProperty('--diagram-height', Math.max(180, Math.min(420, state.h + 32)) + 'px');
    viewer.classList.add('diagram-interactive'); state.fit();
  }
  dialog.addEventListener('close', () => {
    if (!expanded) return;
    const {state, wrap, placeholder, button} = expanded;
    placeholder.replaceWith(wrap); expanded = null; state.fit(); button.focus({preventScroll: true});
  });
  document.addEventListener('planhtml:diagrams-ready', () => $$('.diagram-viewer').forEach(initDiagram));
})();
