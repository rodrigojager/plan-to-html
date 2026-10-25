/* The reader never fetches plan content or requires a web server. */
(() => {
  'use strict';
  const data = JSON.parse(document.getElementById('plan-data').textContent);
  const labels = data.labels;
  const $ = selector => document.querySelector(selector);
  const $$ = selector => [...document.querySelectorAll(selector)];
  const storage = {
    get(key) { try { return localStorage.getItem(key); } catch { return null; } },
    set(key, value) { try { localStorage.setItem(key, value); } catch { /* file storage may be disabled */ } }
  };
  const root = document.documentElement;
  const themeButton = $('#theme-toggle');
  let diagramGeneration = 0;
  let diagramQueue = Promise.resolve();
  const mermaid = window.mermaid || (typeof __esbuild_esm_mermaid_nm !== 'undefined' && (__esbuild_esm_mermaid_nm.mermaid.default || __esbuild_esm_mermaid_nm.mermaid));

  function renderDiagrams() {
    if (!mermaid || !$('.mermaid')) return Promise.resolve();
    const generation = ++diagramGeneration;
    diagramQueue = diagramQueue.catch(() => {}).then(async () => {
      if (generation !== diagramGeneration) return;
      const style = getComputedStyle(root);
      const color = name => style.getPropertyValue(name).trim();
      mermaid.initialize({startOnLoad: false, securityLevel: 'strict', theme: 'base', suppressErrorRendering: true,
        fontFamily: color('--font'), flowchart: {htmlLabels: false, useMaxWidth: true, curve: 'basis'},
        themeVariables: {darkMode: root.dataset.theme === 'dark', background: color('--surface'), primaryColor: color('--accent-soft'), primaryTextColor: color('--text'), primaryBorderColor: color('--accent'), secondaryColor: color('--surface-2'), secondaryTextColor: color('--text'), tertiaryColor: color('--surface'), tertiaryTextColor: color('--text'), lineColor: color('--muted'), textColor: color('--text'), edgeLabelBackground: color('--surface'), mainBkg: color('--accent-soft'), nodeBorder: color('--accent'), fontSize: '13px'}});
      for (const [index, element] of $$('.mermaid').entries()) {
        if (generation !== diagramGeneration) return;
        const error = element.closest('.diagram-wrap').querySelector('.diagram-error');
        try {
          const result = await mermaid.render(`mermaid-${generation}-${index}`, element.dataset.diagramSource);
          if (generation !== diagramGeneration) return;
          element.innerHTML = result.svg;
          const svg = element.querySelector('svg');
          if (svg) { svg.setAttribute('role', 'img'); svg.setAttribute('aria-label', element.closest('.enhancement')?.querySelector('h3')?.textContent || 'Diagram'); }
          if (error) error.hidden = true;
        } catch {
          element.replaceChildren();
          if (error) error.hidden = false;
          const source = element.closest('.diagram-wrap').querySelector('details');
          if (source) source.open = true;
        }
      }
      document.dispatchEvent(new CustomEvent('planhtml:diagrams-ready'));
    });
    return diagramQueue;
  }

  function syncTheme() {
    themeButton.setAttribute('aria-checked', String(root.dataset.theme === 'dark'));
  }
  // Optional extension hook for changed styles; no appearance selector is added.
  document.addEventListener('planhtml:styles-changed', async () => {
    await document.fonts.ready;
    await renderDiagrams();
    document.dispatchEvent(new CustomEvent('planhtml:styles-ready'));
  });
  syncTheme();
  themeButton.addEventListener('click', () => {
    root.dataset.theme = root.dataset.theme === 'dark' ? 'light' : 'dark';
    storage.set('planhtml:theme', root.dataset.theme);
    syncTheme(); renderDiagrams();
    document.dispatchEvent(new CustomEvent('planhtml:theme', {detail: {theme: root.dataset.theme}}));
  });
  matchMedia('(prefers-color-scheme: dark)').addEventListener('change', event => {
    if (!storage.get('planhtml:theme')) {
      root.dataset.theme = event.matches ? 'dark' : 'light'; syncTheme(); renderDiagrams();
    }
  });

  const menu = $('#menu-toggle');
  const backdrop = $('#nav-backdrop');
  function closeNav() { document.body.classList.remove('nav-open'); menu.setAttribute('aria-expanded', 'false'); backdrop.hidden = true; }
  menu.addEventListener('click', () => {
    const open = !document.body.classList.contains('nav-open');
    document.body.classList.toggle('nav-open', open); menu.setAttribute('aria-expanded', String(open)); backdrop.hidden = !open;
    if (open) $('.sidebar a')?.focus();
  });
  backdrop.addEventListener('click', closeNav);
  $$('.sidebar a').forEach(link => link.addEventListener('click', closeNav));
  $('#focus-toggle').addEventListener('click', event => {
    closeNav();
    const active = document.body.classList.toggle('focus-mode');
    event.currentTarget.setAttribute('aria-pressed', String(active));
    drawMapEdges();
  });
  $('#print-button').addEventListener('click', () => window.print());

  const readingMap = window.PlanHTMLReadingMap?.mount($('#document-map'), data.graph, labels);
  function drawMapEdges() { readingMap?.redraw(); }

  // TOC and navigation follow the actual scroll position, not a synthetic task status.
  let activeDoc = null;
  const articles = $$('.document');
  const sourceHeadings = $$('.prose [data-section]');
  function showToc(doc) {
    if (activeDoc === doc.id) return;
    activeDoc = doc.id;
    $$('.doc-link').forEach(link => {
      const active = link.dataset.navDoc === doc.id; link.classList.toggle('active', active);
      if (active) link.setAttribute('aria-current', 'location'); else link.removeAttribute('aria-current');
    });
    const toc = $('#toc'); toc.replaceChildren();
    doc.headings.filter(h => h.level > 1 && h.level < 4).forEach(heading => {
      const link = document.createElement('a'); link.href = '#' + heading.id; link.textContent = heading.text;
      if (heading.level > 2) link.className = 'toc-deep'; toc.append(link);
    });
  }
  let frame = false, saveTimer;
  function updateReading() {
    frame = false;
    const total = root.scrollHeight - window.innerHeight;
    const percent = Math.min(100, Math.max(0, total > 0 ? window.scrollY / total * 100 : 100));
    $('#reading-progress').style.width = percent + '%'; $('#toc-progress-bar').style.width = percent + '%'; $('#progress-label').textContent = Math.round(percent) + '%';
    let current = articles[0];
    for (const article of articles) { if (article.getBoundingClientRect().top <= 160) current = article; else break; }
    const doc = data.documents.find(item => item.id === current?.id);
    if (doc) showToc(doc);
    let section = null;
    for (const heading of sourceHeadings) { if (heading.getBoundingClientRect().top <= 165) section = heading; else break; }
    $$('#toc a').forEach(link => link.classList.toggle('active', !!section && link.hash === '#' + section.id));
    clearTimeout(saveTimer);
    saveTimer = setTimeout(() => storage.set('planhtml:position:' + data.id, String(window.scrollY)), 300);
  }
  window.addEventListener('scroll', () => { if (!frame) { frame = true; requestAnimationFrame(updateReading); } }, {passive:true});
  window.addEventListener('resize', () => { updateReading(); drawMapEdges(); });
  // Anchor jumps open collapsed details that contain their target.
  function revealHash() {
    if (!location.hash) return;
    let id; try { id = decodeURIComponent(location.hash.slice(1)); } catch { return; }
    const target = document.getElementById(id);
    if (!target) return;
    let ancestor = target.parentElement;
    while (ancestor) { if (ancestor.tagName === 'DETAILS') ancestor.open = true; ancestor = ancestor.parentElement; }
    requestAnimationFrame(() => target.scrollIntoView());
    window.PlanHTMLTools?.highlight(target);
  }
  window.addEventListener('hashchange', revealHash);

  // Search index is derived from rendered text. Source prose is never duplicated in JSON.
  const index = [];
  const normalize = text => text.normalize('NFD').replace(/[\u0300-\u036f]/g, '').toLowerCase();
  articles.forEach(article => {
    const doc = data.documents.find(item => item.id === article.id);
    let record = {id: doc.id, title: doc.title, document: doc.title, text: ''};
    const prose = article.querySelector('.prose');
    [...prose.children].forEach(element => {
      if (element.matches('[data-section]')) {
        if (record.text.trim()) index.push(record);
        record = {id: element.id, title: element.textContent, document: doc.title, text: ''};
      } else if (!element.matches('.enhancement')) record.text += element.textContent + ' ';
    });
    if (record.text.trim()) index.push(record);
    if (!index.some(item => item.id === doc.id)) index.push({id:doc.id,title:doc.title,document:doc.title,text:''});
  });
  index.forEach(record => { record.normalized = normalize(record.title + ' ' + record.document + ' ' + record.text); });
  const searchDialog = $('#search-dialog'), input = $('#search-input'), results = $('#search-results');
  let selectedResult = -1;
  function emptySearch(message) { const p = document.createElement('p'); p.className = 'search-empty'; p.textContent = message; results.replaceChildren(p); }
  function openSearch() { closeNav(); searchDialog.showModal(); input.focus(); input.select(); if (!input.value) emptySearch(labels.search_start); }
  $$('[data-open-search]').forEach(button => button.addEventListener('click', openSearch));
  function highlighted(element, text, query) {
    // Normalization can change string length; use normalized text only for ranking,
    // and safe text nodes for excerpts instead of injecting HTML.
    const position = text.toLowerCase().indexOf(query.toLowerCase());
    if (position < 0) { element.textContent = text; return; }
    element.append(document.createTextNode(text.slice(0,position)));
    const mark = document.createElement('mark'); mark.textContent = text.slice(position, position+query.length); element.append(mark, document.createTextNode(text.slice(position+query.length)));
  }
  input.addEventListener('input', () => {
    const query = input.value.trim(), terms = normalize(query).split(/\s+/).filter(Boolean);
    selectedResult = -1;
    if (!terms.length) { emptySearch(labels.search_start); return; }
    const matches = index.filter(item => terms.every(term => item.normalized.includes(term))).map(item => ({...item, score:terms.reduce((score,term) => score + (normalize(item.title).includes(term) ? 5 : 1),0)})).sort((a,b) => b.score-a.score).slice(0,35);
    results.replaceChildren();
    if (!matches.length) { emptySearch(labels.no_results); return; }
    matches.forEach(item => {
      const link = document.createElement('a'); link.className = 'search-result'; link.href = '#' + item.id;
      const doc = document.createElement('span'); doc.className = 'search-result-doc'; doc.textContent = item.document;
      const title = document.createElement('div'); title.className = 'search-result-title'; highlighted(title,item.title,query);
      const snippet = document.createElement('p'); snippet.className = 'search-result-excerpt';
      const position = Math.max(0,normalize(item.text).indexOf(terms[0]));
      const start = Math.max(0,position-65); const excerpt = (start ? '…' : '')+item.text.slice(start,start+220)+(item.text.length>start+220?'…':''); highlighted(snippet,excerpt,query);
      link.append(doc,title,snippet); link.addEventListener('click', () => { searchDialog.close(); if (location.hash === link.hash) revealHash(); }); results.append(link);
    });
  });
  searchDialog.addEventListener('keydown', event => {
    const items = [...results.querySelectorAll('a')];
    if (event.key === 'ArrowDown' || event.key === 'ArrowUp') {
      event.preventDefault(); if (!items.length) return;
      selectedResult = (selectedResult+(event.key==='ArrowDown'?1:-1)+items.length)%items.length;
      items.forEach((item,index) => item.classList.toggle('selected',index===selectedResult));
      items[selectedResult].scrollIntoView({block:'nearest'});
    } else if (event.key === 'Enter' && document.activeElement === input && items.length) {
      event.preventDefault(); items[Math.max(0,selectedResult)].click();
    }
  });
  document.addEventListener('keydown', event => {
    if ((event.ctrlKey || event.metaKey) && event.key.toLowerCase() === 'k') { event.preventDefault(); if (!searchDialog.open) openSearch(); }
    if (event.key === 'Escape') {
      const modal = document.querySelector('dialog[open]');
      if (modal) { event.preventDefault(); modal.close(); }
      closeNav();
    }
  });
  $$('[data-close-dialog]').forEach(button => button.addEventListener('click', () => document.getElementById(button.dataset.closeDialog).close()));
  $$('dialog').forEach(dialog => dialog.addEventListener('click', event => {
    const bounds = dialog.getBoundingClientRect();
    if (event.clientX < bounds.left || event.clientX > bounds.right || event.clientY < bounds.top || event.clientY > bounds.bottom) dialog.close();
  }));
  // Trap keyboard focus inside the open mobile navigation.
  document.addEventListener('keydown', event => {
    if (event.key !== 'Tab' || !document.body.classList.contains('nav-open')) return;
    const items = [menu, ...$$('.sidebar a')]; const first = items[0], last = items.at(-1);
    if (event.shiftKey && document.activeElement === first) { event.preventDefault(); last.focus(); }
    if (!event.shiftKey && document.activeElement === last) { event.preventDefault(); first.focus(); }
  });

  const imageDialog = $('#image-dialog');
  function zoomImage(image) {
    $('#zoom-image').src = image.src; $('#zoom-image').alt = image.alt;
    $('#image-title').textContent = image.alt; $('#image-download').href = image.src; imageDialog.showModal();
  }
  $$('img.zoomable').forEach(image => {
    image.addEventListener('click', () => zoomImage(image));
    image.addEventListener('keydown', event => { if (event.key==='Enter' || event.key===' ') { event.preventDefault(); zoomImage(image); } });
  });
  let toastTimer;
  function toast(message) { const element = $('#toast'); element.textContent = message; element.hidden = false; clearTimeout(toastTimer); toastTimer = setTimeout(() => { element.hidden = true; },1800); }
  $$('.copy-code').forEach(button => button.addEventListener('click', async () => {
    const text = button.closest('.code-block').querySelector('code').textContent;
    try { await navigator.clipboard.writeText(text); }
    catch {
      const textarea = document.createElement('textarea'); textarea.value = text; textarea.style.position='fixed'; textarea.style.opacity='0'; document.body.append(textarea); textarea.select(); document.execCommand('copy'); textarea.remove(); button.focus();
    }
    toast(labels.copied);
  }));

  // Restore only after images and diagrams have settled, and never override a deep link.
  const initialPosition = Number(storage.get('planhtml:position:' + data.id) || 0);
  async function ready() {
    // Separate extension files (including deferred modules) must attach their hooks first.
    if (document.readyState === 'loading') await new Promise(resolve => document.addEventListener('DOMContentLoaded',resolve,{once:true}));
    await document.fonts.ready;
    await renderDiagrams();
    await Promise.all($$('img:not([loading="lazy"])').map(image => image.decode().catch(() => {})));
    if (location.hash) revealHash(); else if (initialPosition > 0) window.scrollTo(0,initialPosition);
    updateReading(); drawMapEdges();
    document.dispatchEvent(new CustomEvent('planhtml:ready', {detail:{documents:data.documents.length}}));
    root.dataset.readerReady = 'true';
  }
  ready();
})();
