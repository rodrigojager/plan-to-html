/* Explicit Markdown links only. Geometry, focus and routing require no model or network. */
(() => {
  'use strict';
  const NS = 'http://www.w3.org/2000/svg';
  const svg = (tag, attributes = {}) => {
    const element = document.createElementNS(NS, tag);
    for (const [key, value] of Object.entries(attributes)) element.setAttribute(key, value);
    return element;
  };
  const node = (tag, className, text) => {
    const element = document.createElement(tag); element.className = className;
    if (text !== undefined) element.textContent = text;
    return element;
  };

  // Opposite directed links share one physical connector, retaining both arrowheads.
  function connections(graph) {
    const order = new Map(graph.nodes.map((item, index) => [item.id, index]));
    const pairs = new Map();
    for (const [from, to] of graph.edges) {
      if (from === to || !order.has(from) || !order.has(to)) continue;
      const [a, b] = order.get(from) < order.get(to) ? [from, to] : [to, from];
      const key = JSON.stringify([a, b]);
      if (!pairs.has(key)) pairs.set(key, {a, b, forward: false, backward: false});
      pairs.get(key)[from === a ? 'forward' : 'backward'] = true;
    }
    return [...pairs.values()].sort((a, b) => order.get(a.a) - order.get(b.a) || order.get(a.b) - order.get(b.b));
  }

  function clearRoute(points, boxes) {
    for (let i = 1; i < points.length; i++) {
      const [x1, y1] = points[i - 1], [x2, y2] = points[i];
      for (const box of boxes) {
        if (Math.abs(y1 - y2) < .1) {
          if (y1 > box.top - 1 && y1 < box.bottom + 1 && Math.max(x1, x2) > box.left - 1 && Math.min(x1, x2) < box.right + 1) return false;
        } else if (Math.abs(x1 - x2) < .1) {
          if (x1 > box.left - 1 && x1 < box.right + 1 && Math.max(y1, y2) > box.top - 1 && Math.min(y1, y2) < box.bottom + 1) return false;
        } else return false;
      }
    }
    return true;
  }

  function routes(items, edges, bounds) {
    const boxes = items.map(item => {
      const r = item.element.getBoundingClientRect();
      return {...item, left: r.left - bounds.left, right: r.right - bounds.left,
        top: r.top - bounds.top, bottom: r.bottom - bounds.top, width: r.width, height: r.height};
    });
    const rows = [];
    for (const box of boxes) {
      let row = rows.find(row => Math.abs(row.top - box.top) < 1);
      if (!row) { row = {top: box.top, bottom: box.bottom, boxes: []}; rows.push(row); }
      row.bottom = Math.max(row.bottom, box.bottom); row.boxes.push(box); box.row = rows.indexOf(row);
    }
    if (!rows.length) return [];
    const byId = new Map(boxes.map(box => [box.id, box]));
    const columns = rows.reduce((longest, row) => row.boxes.length > longest.length ? row.boxes : longest, []);
    const vertical = [{center: columns[0].left / 2, span: columns[0].left, used: 0}];
    for (let i = 1; i < columns.length; i++) vertical.push({center: (columns[i - 1].right + columns[i].left) / 2, span: columns[i].left - columns[i - 1].right, used: 0});
    vertical.push({center: (columns.at(-1).right + bounds.width) / 2, span: bounds.width - columns.at(-1).right, used: 0});
    const horizontal = [{center: rows[0].top / 2, span: rows[0].top, used: 0}];
    for (let i = 1; i < rows.length; i++) horizontal.push({center: (rows[i - 1].bottom + rows[i].top) / 2, span: rows[i].top - rows[i - 1].bottom, used: 0});
    horizontal.push({center: (rows.at(-1).bottom + bounds.height) / 2, span: bounds.height - rows.at(-1).bottom, used: 0});
    // Five bounded lanes keep repeated paths apart without entering a card.
    const lane = channel => channel.center + [0, 1, -1, 2, -2][channel.used % 5] * Math.min(2.5, Math.max(0, channel.span / 2 - 7) / 2);
    const planned = edges.filter(edge => byId.has(edge.a) && byId.has(edge.b)).map(edge => {
      const a = byId.get(edge.a), b = byId.get(edge.b);
      if (a.row !== b.row) return {...edge, aBox: a, bBox: b, aSide: a.row < b.row ? 'bottom' : 'top', bSide: a.row < b.row ? 'top' : 'bottom'};
      const adjacent = Math.abs(rows[a.row].boxes.indexOf(a) - rows[a.row].boxes.indexOf(b)) === 1;
      return {...edge, aBox: a, bBox: b, aSide: adjacent ? 'right' : 'top', bSide: adjacent ? 'left' : 'top'};
    });
    const ports = new Map();
    for (const edge of planned) for (const end of ['a', 'b']) {
      const key = JSON.stringify([edge[end], edge[end + 'Side']]);
      if (!ports.has(key)) ports.set(key, []);
      ports.get(key).push({edge, end});
    }
    for (const group of ports.values()) group.forEach(({edge, end}, index) => {
      const box = edge[end + 'Box'], side = edge[end + 'Side'], ratio = .15 + .7 * (index + 1) / (group.length + 1);
      edge[end + 'Port'] = side === 'left' || side === 'right'
        ? [side === 'left' ? box.left - 4 : box.right + 4, box.top + box.height * ratio]
        : [box.left + box.width * ratio, side === 'top' ? box.top - 4 : box.bottom + 4];
    });
    return planned.map(edge => {
      const {aBox: a, bBox: b, aPort: start, bPort: end} = edge;
      let points;
      if (edge.aSide === 'right') {
        const x = (a.right + b.left) / 2;
        points = [start, [x, start[1]], [x, end[1]], end];
      } else {
        const first = horizontal[a.row + (edge.aSide === 'bottom' ? 1 : 0)];
        const last = horizontal[b.row + (edge.bSide === 'bottom' ? 1 : 0)];
        const y1 = lane(first), y2 = first === last ? y1 : lane(last);
        if (first === last) points = [start, [start[0], y1], [end[0], y1], end];
        else {
          const candidates = [...vertical].sort((c, d) =>
            (Math.abs(start[0] - c.center) + Math.abs(end[0] - c.center) + c.used * 35)
            - (Math.abs(start[0] - d.center) + Math.abs(end[0] - d.center) + d.used * 35));
          for (const channel of candidates) {
            const x = lane(channel), trial = [start, [start[0], y1], [x, y1], [x, y2], [end[0], y2], end];
            if (clearRoute(trial, boxes)) { points = trial; channel.used++; break; }
          }
        }
        first.used++; if (first !== last) last.used++;
      }
      // A custom layout must never cause a line to cross text. Retain an explicit
      // linked-list fallback for any connection that has no collision-free route.
      return {...edge, points: points && clearRoute(points, boxes) ? points : null};
    });
  }

  function mount(map, graph, labels) {
    if (!map) return {redraw() {}};
    const edges = connections(graph), items = new Map();
    const neighbors = new Map(graph.nodes.map(item => [item.id, new Set([item.id])]));
    edges.forEach(edge => { neighbors.get(edge.a).add(edge.b); neighbors.get(edge.b).add(edge.a); });
    const dense = graph.nodes.length > 9 || edges.length > 18;
    let expanded = graph.nodes.length <= 9, hovered = null, focused = null, pinned = null, pending = false;
    const active = () => pinned || focused || hovered;
    const tools = node('div', 'map-tools');
    const hint = node('p', 'map-hint', labels.map_focus_hint); hint.id = 'map-focus-help';
    const reset = node('button', 'map-reset', labels.map_show_all); reset.type = 'button'; reset.disabled = true;
    tools.append(hint, reset);
    const canvas = node('div', 'map-layout'); canvas.setAttribute('aria-describedby', hint.id);
    const drawing = svg('svg', {class: 'map-edges', 'aria-hidden': 'true'}), grid = node('div', 'map-grid');
    const fallback = node('ul', 'map-link-list'); fallback.hidden = true;
    canvas.append(drawing, grid); map.append(tools, canvas, fallback);
    let more;

    function redraw() {
      pending = false;
      if (!canvas.clientWidth) return;
      const id = active();
      map.dataset.mapFocus = id || ''; map.dataset.mapDense = String(dense);
      const related = id ? neighbors.get(id) : null;
      for (const [key, item] of items) {
        item.element.classList.toggle('map-unrelated', !!related && !related.has(key));
        item.element.classList.toggle('map-selected', id === key);
        item.pin.setAttribute('aria-pressed', String(pinned === key));
      }
      reset.disabled = !id;
      drawing.replaceChildren(); fallback.replaceChildren(); fallback.hidden = true;
      // Large graphs start with a document overview; draw only the selected
      // neighborhood rather than a wall of connectors between all documents.
      if (dense && !id) { map.dataset.mapReady = 'true'; return; }
      const markerId = 'reading-map-arrow';
      const defs = svg('defs'), marker = svg('marker', {id: markerId, viewBox: '0 -4 8 8', refX: '8', refY: '0', markerWidth: '6', markerHeight: '6', orient: 'auto-start-reverse', markerUnits: 'userSpaceOnUse'});
      marker.append(svg('path', {d: 'M0,-3 L8,0 L0,3 Z', fill: 'context-stroke'})); defs.append(marker); drawing.append(defs);
      const visible = [...items.values()].filter(item => !item.element.hidden);
      const chosen = id ? edges.filter(edge => edge.a === id || edge.b === id) : edges;
      const laidOut = routes(visible, chosen, canvas.getBoundingClientRect());
      for (const edge of laidOut) {
        if (!edge.points) {
          const entry = node('li', '');
          for (const [index, key] of [edge.a, edge.b].entries()) {
            if (index) entry.append(document.createTextNode(edge.forward && edge.backward ? ' ↔ ' : edge.forward ? ' → ' : ' ← '));
            const link = node('a', '', items.get(key).title); link.href = '#' + key; entry.append(link);
          }
          fallback.append(entry); fallback.hidden = false; continue;
        }
        const group = svg('g', {'data-from': edge.a, 'data-to': edge.b, class: id ? 'map-edge active-edge' : 'map-edge'});
        const d = edge.points.map(([x, y], index) => `${index ? 'L' : 'M'}${x.toFixed(2)},${y.toFixed(2)}`).join(' ');
        const line = svg('path', {d, class: 'map-edge-line'});
        if (edge.forward) line.setAttribute('marker-end', `url(#${markerId})`);
        if (edge.backward) line.setAttribute('marker-start', `url(#${markerId})`);
        group.append(svg('path', {d, class: 'map-edge-halo'}), line); drawing.append(group);
      }
      map.dataset.mapReady = 'true';
    }
    function schedule() {
      map.dataset.mapReady = 'false';
      if (!pending) { pending = true; requestAnimationFrame(redraw); }
    }
    function clear() { pinned = focused = hovered = null; schedule(); }
    reset.addEventListener('click', clear);
    document.addEventListener('keydown', event => {
      if (event.key === 'Escape' && active() && !document.querySelector('dialog[open]')) { event.preventDefault(); clear(); }
    });
    map.addEventListener('pointerleave', () => { hovered = null; schedule(); });
    map.addEventListener('focusout', event => {
      if (!map.contains(event.relatedTarget)) { focused = null; schedule(); }
    });
    function expand(value) {
      expanded = value;
      [...items.values()].forEach((item, index) => { item.element.hidden = !expanded && index >= 9; });
      if (more) { more.textContent = expanded ? labels.map_collapse : `+ ${graph.nodes.length - 9} ${labels.document_unit}`; more.setAttribute('aria-expanded', String(expanded)); }
      schedule();
    }
    graph.nodes.forEach((item, index) => {
      const card = node('div', 'map-item'); card.hidden = !expanded && index >= 9;
      const anchor = node('a', 'map-node'); anchor.href = '#' + item.id; anchor.dataset.mapId = item.id;
      const number = node('span', '', String(index + 1).padStart(2, '0'));
      const title = node('span', '', item.title); title.append(node('small', '', item.kind)); anchor.append(number, title);
      const pin = node('button', 'map-select'); pin.type = 'button'; pin.dataset.mapSelect = item.id;
      pin.setAttribute('aria-label', `${labels.map_pin}: ${item.title}`); pin.title = labels.map_pin; pin.setAttribute('aria-pressed', 'false');
      const icon = svg('svg', {viewBox: '0 0 16 16', 'aria-hidden': 'true', width: '14', height: '14'});
      icon.append(svg('path', {d: 'M8 2v12M2 8h12M4 4h8v8H4Z', fill: 'none', stroke: 'currentColor', 'stroke-width': '1.2'})); pin.append(icon);
      card.append(anchor, pin); grid.append(card); items.set(item.id, {id: item.id, title: item.title, element: card, pin});
      // Layout changes can emit pointerenter under a stationary cursor. Only an
      // actual pointer move may replace a keyboard selection or reveal neighbors.
      card.addEventListener('pointermove', event => {
        if (event.pointerType !== 'touch' && (hovered !== item.id || focused)) { hovered = item.id; focused = null; schedule(); }
      });
      card.addEventListener('pointerleave', () => { if (hovered === item.id) { hovered = null; schedule(); } });
      card.addEventListener('focusin', () => { focused = item.id; hovered = null; schedule(); });
      card.addEventListener('focusout', event => { if (!card.contains(event.relatedTarget)) { focused = null; schedule(); } });
      pin.addEventListener('click', () => {
        const next = pinned === item.id ? null : item.id;
        focused = hovered = null; pinned = next;
        if (pinned && !expanded) expand(true);
        schedule();
      });
    });
    if (graph.nodes.length > 9) {
      more = node('button', 'map-more', `+ ${graph.nodes.length - 9} ${labels.document_unit}`); more.type = 'button';
      more.setAttribute('aria-expanded', 'false'); more.setAttribute('aria-controls', 'document-map-grid'); grid.id = 'document-map-grid';
      more.addEventListener('click', () => { clear(); expand(!expanded); }); tools.append(more);
    }
    const observer = new ResizeObserver(schedule); observer.observe(canvas);
    for (const item of items.values()) observer.observe(item.element);
    document.fonts.addEventListener('loadingdone', schedule);
    document.addEventListener('planhtml:styles-ready', schedule);
    schedule();
    return {redraw: schedule};
  }
  window.PlanHTMLReadingMap = {mount};
})();
