/* Local, demo-only selector. Theme CSS files remain independently usable at build time. */
(() => {
  'use strict';
  const catalog = JSON.parse(document.getElementById('preview-theme-data').textContent);
  const root = document.documentElement;
  const selector = document.getElementById('preview-theme-select');
  const toolbar = document.getElementById('theme-preview');
  const toggle = document.getElementById('preview-collapse');
  const content = document.getElementById('preview-controls');
  const links = [...document.querySelectorAll('link[data-preview-theme]')];
  let revision = 0;
  let active = catalog.themes[0];
  function samples() {
    const colors = active[root.dataset.theme === 'dark' ? 'dark' : 'light'];
    [...document.querySelectorAll('.theme-preview-samples span')].forEach((span, index) => { span.style.backgroundColor = colors[[0, 1, 3, 7][index]]; });
  }
  async function apply(id, preserve = true) {
    const theme = catalog.themes.find(item => item.id === id) || catalog.themes.find(item => item.id === catalog.preview_default) || catalog.themes[0];
    const currentRevision = ++revision;
    root.dataset.previewReady = 'false';
    const anchor = preserve ? [...document.querySelectorAll('.hero, .reading-map, .prose > *')].find(element => {
      const bounds = element.getBoundingClientRect(); return bounds.bottom > 150 && bounds.top < innerHeight;
    }) : null;
    const previousTop = anchor?.getBoundingClientRect().top;
    active = theme; selector.value = theme.id;
    root.dataset.previewTheme = theme.id;
    document.getElementById('preview-theme-note').textContent = theme.note;
    document.getElementById('preview-theme-position').textContent = `${catalog.themes.indexOf(theme) + 1} / ${catalog.themes.length}`;
    for (const link of links) link.media = link.dataset.previewTheme === theme.id ? 'all' : 'not all';
    try { localStorage.setItem('planhtml:preview-theme', theme.id); } catch { /* optional preference */ }
    samples();
    const stylesheet = links.find(link => link.dataset.previewTheme === theme.id);
    if (!stylesheet.sheet) await new Promise((resolve, reject) => { stylesheet.addEventListener('load', resolve, {once: true}); stylesheet.addEventListener('error', reject, {once: true}); });
    await new Promise(requestAnimationFrame);
    await Promise.all(['.hero h1', '.prose'].map(selector => {
      const css = getComputedStyle(document.querySelector(selector));
      return document.fonts.load(`${css.fontWeight} ${css.fontSize} ${css.fontFamily}`);
    }));
    await document.fonts.ready;
    if (currentRevision !== revision) return;
    if (anchor) window.scrollBy(0, anchor.getBoundingClientRect().top - previousTop);
    const ready = new Promise(resolve => document.addEventListener('planhtml:styles-ready', resolve, {once: true}));
    document.dispatchEvent(new CustomEvent('planhtml:styles-changed'));
    await ready;
    if (currentRevision !== revision) return;
    window.dispatchEvent(new Event('resize'));
    root.dataset.previewReady = 'true';
  }
  selector.addEventListener('change', () => apply(selector.value));
  function step(delta) {
    const index = catalog.themes.findIndex(theme => theme.id === selector.value);
    apply(catalog.themes[(index + delta + catalog.themes.length) % catalog.themes.length].id);
  }
  document.getElementById('preview-previous').addEventListener('click', () => step(-1));
  document.getElementById('preview-next').addEventListener('click', () => step(1));
  toggle.addEventListener('click', () => {
    const compact = toolbar.classList.toggle('compact'); content.hidden = compact;
    toggle.setAttribute('aria-expanded', String(!compact));
    toggle.setAttribute('aria-label', compact ? 'Mostrar seletor de temas' : 'Recolher seletor de temas');
    toggle.textContent = compact ? '+' : '−';
  });
  document.addEventListener('planhtml:theme', samples);
  let preferred;
  try { preferred = localStorage.getItem('planhtml:preview-theme'); } catch { /* optional preference */ }
  apply(preferred, false);
})();
