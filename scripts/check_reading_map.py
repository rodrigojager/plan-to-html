#!/usr/bin/env python3
"""Behavioral/geometry regression for dense, relocated and offline reading maps."""
import hashlib
import json
from pathlib import Path
import re
import shutil
import subprocess
import sys
import tempfile

from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parents[1]


def build(source, output, theme='default'):
    result = subprocess.run([sys.executable, str(ROOT / 'scripts/plan_html.py'), 'build', str(source),
                             '--output', str(output), '--theme', theme, '--format', 'single'],
                            capture_output=True, text=True, encoding='utf-8')
    assert result.returncode == 0, result.stderr
    report = json.loads(output.with_suffix('.bundle.json').read_text(encoding='utf-8'))
    assert report['self_contained_static_resources'] and not report['external_resources']


def settle(page, selected=None):
    page.evaluate('()=>new Promise(resolve=>requestAnimationFrame(()=>requestAnimationFrame(resolve)))')
    page.wait_for_function('id=>{const d=document.querySelector("#document-map").dataset;return d.mapReady==="true"&&(id===null||d.mapFocus===id)}', arg=selected)


def card_positions(page):
    return page.evaluate('''()=>{
        const b=document.querySelector('.map-layout').getBoundingClientRect();
        return [...document.querySelectorAll('.map-item')].filter(e=>!e.hidden).map(e=>{
          const r=e.getBoundingClientRect();return [r.left-b.left,r.top-b.top,r.width,r.height];
        });
    }''')


def geometry(page):
    state = page.evaluate('''()=>{
        const canvas=document.querySelector('.map-layout'), b=canvas.getBoundingClientRect();
        return {boxes:[...canvas.querySelectorAll('.map-item')].filter(e=>!e.hidden).map(e=>{
          const r=e.querySelector('.map-node').getBoundingClientRect();
          return {left:r.left-b.left,right:r.right-b.left,top:r.top-b.top,bottom:r.bottom-b.top};
        }),paths:[...canvas.querySelectorAll('.map-edge-line')].map(e=>e.getAttribute('d')),
          layer:getComputedStyle(canvas.querySelector('.map-edges')).zIndex,
          hitTesting:getComputedStyle(canvas.querySelector('.map-edges')).pointerEvents};
    }''')
    assert state['layer'] == '2' and state['hitTesting'] == 'none'
    for path in state['paths']:
        points = [(float(x), float(y)) for x, y in re.findall(r'[ML](-?[\d.]+),(-?[\d.]+)', path)]
        assert len(points) >= 2
        for (x1, y1), (x2, y2) in zip(points, points[1:]):
            assert abs(x1-x2) < .1 or abs(y1-y2) < .1, path
            for box in state['boxes']:
                if abs(y1-y2) < .1:
                    crosses = box['top']+.1 < y1 < box['bottom']-.1 and max(x1, x2) > box['left']+.1 and min(x1, x2) < box['right']-.1
                else:
                    crosses = box['left']+.1 < x1 < box['right']-.1 and max(y1, y2) > box['top']+.1 and min(y1, y2) < box['bottom']-.1
                assert not crosses, ('Connector crosses a card', path, box)
    return len(state['paths'])


def main():
    errors, requests, cases = [], [], []
    screenshots = ROOT / '.test-output/map-regression'
    screenshots.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix='reading-map-check-') as temporary:
        folder = Path(temporary)
        source = folder / 'source'; source.mkdir()
        (source / 'PLAN.md').write_text('# Plano com muitos documentos\n\n' + '\n'.join(f'- [Parte {i:02d}]({i:02d}.md)' for i in range(1, 20)), encoding='utf-8')
        links = {1: ['PLAN.md', '02.md', '03.md'], 2: ['01.md', '04.md'], 10: ['01.md']}
        for i in range(1, 21):
            title = f'Parte {i:02d}: contratos, critérios e referências com título comprido'
            (source / f'{i:02d}.md').write_text('# ' + title + '\n\nTexto original da parte.\n\n' + '\n'.join(f'[Referência]({target})' for target in links.get(i, [])), encoding='utf-8')
        hashes = {p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in source.glob('*.md')}
        pages = []
        for theme in ('default', 'maximalista'):
            output = folder / (theme + '.html'); build(source, output, theme)
            pages.append((theme, output))
        small = folder / 'small'; small.mkdir()
        (small / 'PLAN.md').write_text('# Pequeno\n\n[Parte A](a.md)\n\n[Parte B](b.md)', encoding='utf-8')
        for name in ('a', 'b'):
            (small / (name + '.md')).write_text('# Parte ' + name + '\n\n[Voltar](PLAN.md)', encoding='utf-8')
        small_output = folder / 'small.html'; build(small, small_output)
        assert hashes == {p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in source.glob('*.md')}
        # Only final HTML files survive relocation. All source/assets disappear.
        relocated = folder / 'relocated'; relocated.mkdir()
        for _, output in pages:
            shutil.move(str(output), str(relocated / output.name))
        shutil.move(str(small_output), str(relocated / small_output.name))
        shutil.rmtree(source); shutil.rmtree(small)
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            context = browser.new_context(viewport={'width': 1512, 'height': 1000}, color_scheme='light', reduced_motion='reduce', has_touch=True)
            context.route('http://**/*', lambda r: (requests.append(r.request.url), r.abort()))
            context.route('https://**/*', lambda r: (requests.append(r.request.url), r.abort()))
            page = context.new_page(); page.set_default_timeout(15000)
            page.on('pageerror', lambda error: errors.append(str(error)))
            page.on('requestfailed', lambda request: errors.append('Resource failed: ' + request.url[:100]))
            for theme, output in pages:
                page.goto((relocated / output.name).as_uri())
                page.wait_for_selector('html[data-reader-ready="true"]', state='attached', timeout=45000)
                settle(page, '')
                graph = page.locator('#plan-data').evaluate('e=>JSON.parse(e.textContent).graph')
                ids = [item['id'] for item in graph['nodes']]
                chosen = ids[1]
                related = {chosen} | {to if frm == chosen else frm for frm, to in graph['edges'] if chosen in (frm, to)}
                assert len(related) == 5, related
                assert page.locator('.map-item:visible').count() == 9
                assert not page.locator('.map-edge-line').count(), 'Dense overview still draws all edges'
                page.locator('.map-more').click(); settle(page, '')
                assert page.locator('.map-item:visible').count() == 21
                page.locator('.map-more').click(); settle(page, '')
                assert page.locator('.map-item:visible').count() == 9
                # Pin works with actual touch events and reveals related documents beyond the initial nine.
                page.locator(f'[data-map-select="{chosen}"]').tap(); settle(page, chosen)
                assert not page.locator('.map-more').get_attribute('aria-expanded') == 'false'
                page.mouse.move(0, 0); settle(page, chosen)
                assert page.locator('.map-item:visible').count() == len(related)
                assert geometry(page) == len(related) - 1
                page.locator('.map-reset').click(); settle(page, '')
                assert page.locator('.map-item:visible').count() == 21
                for width in (1512, 1000, 360):
                    page.set_viewport_size({'width': width, 'height': 1000})
                    settle(page, '')
                    for mode in ('light', 'dark'):
                        if page.locator('html').get_attribute('data-theme') != mode:
                            page.locator('#theme-toggle').click(); settle(page, '')
                        before = card_positions(page)
                        page.locator(f'[data-map-id="{chosen}"]').hover(); settle(page, chosen)
                        visible_ids = page.locator('.map-item:visible .map-node').evaluate_all('items=>items.map(e=>e.dataset.mapId)')
                        assert set(visible_ids) == related, ('Incorrect neighborhood', visible_ids, related)
                        assert before == card_positions(page), 'Focus rearranged cards'
                        assert geometry(page) == len(related) - 1
                        assert not page.locator('.map-link-list li').count(), 'Ordinary grid routing required a fallback'
                        assert page.evaluate('document.documentElement.scrollWidth<=innerWidth+1'), 'Mobile overflow'
                        cases.append(f'{theme}/{width}/{mode}')
                        if width in (1512, 360):
                            page.screenshot(path=str(screenshots / f'{theme}-{width}-{mode}.png'))
                        page.locator('.map-reset').click(); settle(page, '')
                # Keyboard focus isolates, Escape restores, and pinned selection survives pointer movement.
                page.locator(f'[data-map-id="{chosen}"]').focus(); settle(page, chosen)
                page.locator(f'[data-map-id="{ids[0]}"]').hover(); settle(page, ids[0])
                page.keyboard.press('Escape'); settle(page, '')
                page.locator(f'[data-map-select="{chosen}"]').focus(); settle(page, chosen)
                page.keyboard.press('Enter'); settle(page, chosen)
                page.mouse.move(0, 0); settle(page, chosen)
                assert page.locator(f'[data-map-select="{chosen}"]').get_attribute('aria-pressed') == 'true'
                page.locator('.map-reset').click(); settle(page, '')
                page.locator(f'[data-map-id="{ids[-1]}"]').focus(); settle(page, ids[-1])
                assert page.locator('.map-item:visible').count() == 1 and not page.locator('.map-edge-line').count(), 'Isolated node gained invented relationships'
                page.emulate_media(media='print')
                assert page.locator('.map-item:visible').count() == 21
                assert page.locator('.map-select').first.is_hidden()
                page.emulate_media(media='screen')
                page.keyboard.press('Escape'); settle(page, '')
                page.locator('.map-more').click(); settle(page, '')
                assert page.locator('.map-item:visible').count() == 9
                print('Dense map, geometry, keyboard, touch and print:', theme, flush=True)
            page.goto((relocated / small_output.name).as_uri())
            page.wait_for_selector('html[data-reader-ready="true"]', state='attached')
            settle(page, '')
            assert page.locator('.map-edge-line').count() == 2, 'Reciprocal edges were duplicated'
            assert page.locator('.map-edge-line[marker-start][marker-end]').count() == 2
            assert geometry(page) == 2
            first = page.locator('.map-node').first
            first.focus(); settle(page, first.get_attribute('data-map-id'))
            first.click(); assert 'doc-' in page.url, 'Title link no longer navigates'
            # Redraw after font metrics/row height change.
            page.add_style_tag(content='.map-node {font-size:19px !important}')
            settle(page)
            assert geometry(page) == 2
            # An incompatible extra layout must keep relationships as linked pairs,
            # instead of drawing a connector through overlapping cards.
            page.add_style_tag(content='.map-item:nth-child(2) {left:-120px}')
            page.evaluate('window.dispatchEvent(new Event("resize"))'); settle(page)
            assert page.locator('.map-link-list li').count() > 0
            geometry(page)
            browser.close()
    assert not errors, errors
    assert not requests, requests
    report = {'states': cases, 'keyboard': True, 'touch_pin': True, 'collision_checks': True,
              'reciprocal_edges_merged': True, 'isolated_node': True, 'layout_fallback': True,
              'relocated_offline': True, 'source_preserved': True, 'errors': errors, 'network_requests': requests}
    (screenshots / 'acceptance.json').write_text(json.dumps(report, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
