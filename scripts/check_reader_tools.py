#!/usr/bin/env python3
"""Exercise deterministic controls on relocated, offline files with two themes."""
import hashlib
import io
import json
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / '.vendor'))
from PIL import Image
from reader_features import image_dimensions
from themes import validate_theme, resolve_theme
from playwright.sync_api import sync_playwright


def run(*args):
    result = subprocess.run([sys.executable, str(ROOT / 'scripts' / 'plan_html.py'), *args], capture_output=True, text=True, encoding='utf-8')
    assert result.returncode == 0, result.stderr
    return json.loads(result.stdout)


def main():
    errors, network = [], []
    code = 'def total(values):\n    return sum(values)  # keep exact spacing\n\nprint(total([1, 2, 3]))\n'
    output = ROOT / '.test-output'
    output.mkdir(exist_ok=True)
    with tempfile.TemporaryDirectory(prefix='plan-reader-tools-') as temporary:
        folder = Path(temporary)
        source = folder / 'source'; source.mkdir()
        for ext in ('png', 'bmp'):
            Image.new('RGB', (320, 180), '#22805a').save(source / ('image.' + ext))
        jpeg = io.BytesIO()
        exif = Image.Exif(); exif[274] = 6
        Image.new('RGB', (240, 120), 'white').save(jpeg, format='JPEG', exif=exif)
        assert image_dimensions(jpeg.getvalue()) == {'width': 120, 'height': 240}
        assert image_dimensions(b'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 640 360"/>') == {'width': 640, 'height': 360}
        (source / 'image.svg').write_text('<svg xmlns="http://www.w3.org/2000/svg" width="640" height="360"><rect width="640" height="360" fill="#22805a"/></svg>')
        table = '| Name | A | B | C | D | E |\n|---|---|---|---|---|---|\n' + ''.join(f'| Row {n} | 100 | 200 | 300 | 400 | 500 |\n' for n in range(30))
        markdown = '# Teste dos controles\n\n## Código\n\n```python\n' + code + '```\n\n```unknown-lexer\nplain <text>\n```\n\n```text\n' + 'x' * 600 + '\n```\n\n## Tabela\n\n' + table + '\n## Imagens\n\n![PNG](image.png)\n\n<img src="image.bmp" alt="BMP">\n\n![SVG](image.svg)\n\n## Diagrama\n\n```mermaid\nflowchart LR\n  A[Entrada] --> B[Conversão] --> C[HTML]\n```\n'
        (source / 'PLAN.md').write_text(markdown, encoding='utf-8')
        before = hashlib.sha256((source / 'PLAN.md').read_bytes()).hexdigest()
        # A downloaded theme may carry its own local font, resolved from its CSS directory.
        downloaded = source / 'downloaded.css'
        shutil.copyfile(ROOT / 'assets/fonts/inter-latin-400-normal.woff2', source / 'custom.woff2')
        downloaded.write_text((ROOT / 'themes/slate.css').read_text(encoding='utf-8') + '\n@font-face {font-family: CustomPlan;src:url("custom.woff2") format("woff2");font-weight:400;}\n:root {--font:CustomPlan,"Plan Inter",sans-serif;}\n', encoding='utf-8')
        assert resolve_theme('slate', ROOT) == (ROOT / 'themes/slate.css').resolve()
        bad = source / 'invalid.css'; bad.write_text('button { display:none; }')
        try:
            validate_theme(bad)
            raise AssertionError('Structural theme CSS was accepted')
        except ValueError:
            pass
        for name, theme in [('default', 'default'), ('downloaded', str(downloaded))]:
            run('build', str(source / 'PLAN.md'), '--output', str(folder / (name + '.html')), '--format', 'single', '--theme', theme)
        assert before == hashlib.sha256((source / 'PLAN.md').read_bytes()).hexdigest()
        # Files below must work after every source image/font/theme has disappeared.
        source.rename(folder / 'source-unavailable')
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            for name in ('default', 'downloaded'):
                print('Checking offline reader:', name, flush=True)
                context = browser.new_context(viewport={'width': 1512, 'height': 1000}, color_scheme='light', reduced_motion='reduce')
                context.route('http://**/*', lambda route: (network.append(route.request.url), route.abort()))
                context.route('https://**/*', lambda route: (network.append(route.request.url), route.abort()))
                context.add_init_script('Object.defineProperty(navigator,"clipboard",{value:{writeText:async text=>{window.copiedText=text}}})')
                page = context.new_page()
                page.set_default_timeout(8000)
                page.on('pageerror', lambda error: errors.append(str(error)))
                page.on('requestfailed', lambda request: errors.append('Resource failed: ' + request.url[:100]))
                page.goto((folder / (name + '.html')).as_uri())
                page.wait_for_selector('html[data-reader-ready="true"]', state='attached', timeout=45000)
                assert page.evaluate('document.fonts.check(\'15px "Plan Inter"\') && document.fonts.check(\'12px "Plan Mono"\')'), 'Embedded fonts not loaded'
                if name == 'downloaded':
                    assert page.evaluate('document.fonts.check("15px CustomPlan")')
                    assert page.evaluate('getComputedStyle(document.body).backgroundColor') == 'rgb(244, 246, 250)'
                assert page.locator('.code-block code').first.text_content() == code, 'Highlighting changed code'
                assert page.locator('.language-python .k').count() > 0, 'Declared language not highlighted'
                assert page.locator('.language-unknown-lexer').text_content() == 'plain <text>\n'
                assert page.locator('.language-unknown-lexer .k').count() == 0
                page.locator('.copy-code').first.click()
                page.wait_for_function('(expected)=>window.copiedText===expected', arg=code)
                block = page.locator('.code-block').nth(2)
                block.locator('.code-wrap-toggle').click()
                assert block.locator('pre').evaluate('e=>e.scrollWidth<=e.clientWidth+1'), 'Wrapped code still overflows'
                block.locator('.code-lines-toggle').click()
                assert block.locator('.code-line').first.evaluate('e=>getComputedStyle(e,"::before").display') == 'none'
                heading = page.locator('.heading-anchor').first
                anchor = heading.get_attribute('data-anchor')
                heading.focus(); heading.click()
                page.wait_for_function('(id)=>decodeURIComponent(new URL(window.copiedText).hash.slice(1))===id', arg=anchor)
                page.evaluate('(id)=>location.hash=id', anchor)
                page.wait_for_selector('.target-highlight')
                print('  code and heading controls passed', flush=True)
                assert page.locator('.heading-anchor').first.evaluate('e=>e.parentElement.textContent') == 'Código'
                images = page.locator('.prose img.zoomable')
                assert images.count() == 3
                assert images.evaluate_all('items=>items.every(e=>Number(e.getAttribute("width"))>0&&Number(e.getAttribute("height"))>0)')
                page.evaluate('document.querySelectorAll("img.zoomable").forEach(e=>e.loading="eager")')
                page.wait_for_function('Array.from(document.querySelectorAll("img.zoomable")).every(e=>e.complete&&e.naturalWidth>0)')
                # Sticky table header must stay at the table viewport, not at the page top.
                table = page.locator('.table-wrap'); table.scroll_into_view_if_needed()
                table.evaluate('e=>{e.style.maxHeight="240px";e.style.width="320px";e.scrollTop=200;e.scrollLeft=150}')
                assert table.locator('th').first.evaluate('e=>getComputedStyle(e).position') == 'sticky'
                assert table.locator('tbody td').first.evaluate('e=>getComputedStyle(e).position') == 'sticky'
                bounds, cell = table.bounding_box(), table.locator('th').first.bounding_box()
                assert abs(cell['y'] - bounds['y']) < 3 and abs(cell['x'] - bounds['x']) < 3, 'Sticky table cells moved out of view'
                row_colors = table.locator('tbody tr td:nth-child(2)').evaluate_all('items=>items.slice(0,2).map(e=>getComputedStyle(e).backgroundColor)')
                assert row_colors[0] != row_colors[1], 'Table stripes missing'
                print('  image metadata and tables passed', flush=True)
                page.locator('#reading-settings').click()
                page.locator('#reading-size').fill('19'); page.locator('#reading-spacing').fill('2.1')
                page.locator('#reading-width').select_option('800px')
                page.keyboard.press('Escape')
                assert page.locator('.prose').first.evaluate('e=>getComputedStyle(e).fontSize') == '19px'
                assert page.locator('.prose').first.evaluate('e=>getComputedStyle(e).lineHeight') == '39.9px'
                page.reload(); page.wait_for_selector('html[data-reader-ready="true"]', state='attached')
                assert page.locator('.prose').first.evaluate('e=>getComputedStyle(e).fontSize') == '19px', 'Reading preferences lost'
                assert page.locator('.content-column').evaluate('e=>getComputedStyle(e).maxWidth') == '800px'
                page.locator('#reading-settings').click(); page.locator('#reading-reset').click(); page.keyboard.press('Escape')
                assert page.locator('.prose').first.evaluate('e=>getComputedStyle(e).fontSize') == '15px'
                print('  saved reading settings passed', flush=True)
                viewer = page.locator('.diagram-viewer'); viewer.scroll_into_view_if_needed()
                viewport = viewer.locator('.diagram-viewport')
                viewer.locator('[data-diagram-action=in]').click()
                assert float(viewport.get_attribute('data-zoom')) > 1
                original = viewer.locator('.mermaid').evaluate('e=>e.style.transform')
                viewport.focus(); page.keyboard.press('ArrowRight')
                assert original != viewer.locator('.mermaid').evaluate('e=>e.style.transform'), 'Keyboard pan failed'
                area = viewport.bounding_box()
                before_drag = viewer.locator('.mermaid').evaluate('e=>e.style.transform')
                page.mouse.move(area['x'] + 40, area['y'] + 40); page.mouse.down(); page.mouse.move(area['x'] + 85, area['y'] + 75); page.mouse.up()
                assert before_drag != viewer.locator('.mermaid').evaluate('e=>e.style.transform'), 'Pointer pan failed'
                page.keyboard.press('0')
                assert float(viewport.get_attribute('data-zoom')) == 1
                viewer.locator('[data-diagram-action=expand]').click()
                assert page.locator('#diagram-dialog').evaluate('e=>e.open')
                assert viewport.bounding_box()['height'] > 600, 'Expanded diagram did not use viewport'
                page.locator('#diagram-dialog [data-diagram-action=in]').click()
                # Theme redraw also works while the viewer is inside the dialog.
                page.evaluate('document.getElementById("theme-toggle").click()')
                page.wait_for_function('document.querySelector(".mermaid svg")?.id.startsWith("mermaid-2-")')
                assert not page.locator('.diagram-error:not([hidden])').count()
                page.keyboard.press('Escape')
                page.wait_for_selector('.prose .diagram-viewer', state='attached')
                assert page.locator('.prose .diagram-viewer').count() == 1, 'Expanded diagram not restored'
                assert page.locator('html').get_attribute('data-theme') == 'dark'
                assert page.locator('#theme-toggle').evaluate('e=>getComputedStyle(e).transitionDuration') == '0s'
                page.emulate_media(reduced_motion='no-preference')
                assert '0.18s' in page.locator('#theme-toggle').evaluate('e=>getComputedStyle(e).transitionDuration')
                page.emulate_media(reduced_motion='reduce', media='print')
                assert page.locator('.diagram-toolbar').is_hidden()
                assert page.evaluate('getComputedStyle(document.body).backgroundColor') == 'rgb(255, 255, 255)'
                assert table.evaluate('e=>getComputedStyle(e).maxHeight') == 'none'
                page.emulate_media(media='screen')
                page.set_viewport_size({'width': 360, 'height': 800})
                page.evaluate('location.hash="overview"')
                assert page.evaluate('document.documentElement.scrollWidth<=innerWidth+1'), 'Mobile page overflow'
                page.locator('#reading-settings').click()
                assert page.locator('#reading-dialog').is_visible()
                page.keyboard.press('Escape')
                page.set_viewport_size({'width': 1512, 'height': 1000})
                viewer.scroll_into_view_if_needed()
                viewer.screenshot(path=str(output / (name + '-diagram.png')))
                context.close()
            browser.close()
    assert not errors, errors
    assert not network, network
    print(json.dumps({'themes': ['default', 'downloaded-css-with-local-font'], 'offline': True, 'checks': ['embedded-fonts', 'exact-code-copy', 'declared-syntax', 'unknown-lexer', 'line-numbers', 'line-wrap', 'heading-link-copy', 'target-highlight', 'image-dimensions', 'raster-and-svg', 'sticky-table', 'table-stripes', 'reading-preferences', 'zoom-pan-fit', 'expanded-diagram', 'theme-redraw', 'reduced-motion', 'print', 'mobile', 'theme-contract', 'unchanged-markdown'], 'errors': errors, 'network_requests': network}, indent=2))


if __name__ == '__main__':
    main()
