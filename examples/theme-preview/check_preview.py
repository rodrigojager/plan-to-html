#!/usr/bin/env python3
"""Offline acceptance of all themes, their normal builds, and the demo-only selector."""
import argparse
import hashlib
import json
import math
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile

from playwright.sync_api import sync_playwright

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
sys.path.insert(0, str(ROOT / '.vendor'))
from PIL import Image, ImageDraw


def contrast(a, b):
    def luminance(value):
        rgb = [int(value[i:i+2], 16) / 255 for i in (1, 3, 5)]
        linear = [v / 12.92 if v <= .04045 else ((v + .055) / 1.055) ** 2.4 for v in rgb]
        return sum(c * v for c, v in zip((.2126, .7152, .0722), linear))
    lo, hi = sorted([luminance(a), luminance(b)])
    return (hi + .05) / (lo + .05)


def wait_preview(page, theme):
    page.wait_for_function('(theme)=>document.documentElement.dataset.previewTheme===theme && document.documentElement.dataset.previewReady==="true"', arg=theme)


def source_text(page):
    # Mermaid includes generated style text/IDs, which change on each render.
    return page.locator('.documents .prose').evaluate_all('items=>items.map(e=>{const c=e.cloneNode(true);c.querySelectorAll(".mermaid").forEach(d=>d.replaceChildren());return c.textContent})')


def interaction_state(page, theme):
    """Test the actual CSS effects and reduced-motion fallback, not just catalog flags."""
    page.emulate_media(reduced_motion='no-preference')
    hover = page.locator('.doc-link:not(.active)').first
    hover.hover()
    state = page.evaluate('''()=>{
        const root=getComputedStyle(document.documentElement), active=document.querySelector('.doc-link.active'),
          hovered=document.querySelector('.doc-link:hover'), s=getComputedStyle(hovered),
          selected=getComputedStyle(active,'::after'), h=getComputedStyle(document.querySelector('.hero h1'));
        return {duration:root.getPropertyValue('--duration').trim(), hoverAnimation:s.animationName,
          hoverShadow:s.boxShadow, hoverTransition:s.transitionProperty, selectedAnimation:selected.animationName,
          selectedMarker:getComputedStyle(active,'::before').opacity, headingFont:h.fontFamily,
          headingFontLoaded:document.fonts.check(`${h.fontWeight} ${h.fontSize} ${h.fontFamily}`)};
    }''')
    props = theme['appearance']
    expected_hover = props.get('hover-animation', 'none').split()[0]
    expected_selected = props.get('selected-animation', 'none').split()[0]
    assert state['hoverAnimation'] == expected_hover, (theme['id'], state)
    assert state['selectedAnimation'] == expected_selected, (theme['id'], state)
    assert state['headingFontLoaded'], (theme['id'], 'Font missing', state)
    assert props['font-heading'].split(',')[0].strip('"') in state['headingFont']
    if props.get('selected-marker-opacity') == '1':
        assert state['selectedMarker'] == '1', (theme['id'], state)
    if props.get('hover-shadow'):
        assert state['hoverShadow'] != 'none', (theme['id'], state)
    if theme['animated']:
        assert state['duration'] != '0ms'
        assert 'transform' in state['hoverTransition'], (theme['id'], state)
    else:
        assert state['duration'] == '0ms', (theme['id'], 'Static theme animates', state)
        assert expected_hover == expected_selected == 'none'
    page.emulate_media(reduced_motion='reduce')
    reduced = hover.evaluate('''e=>({transform:getComputedStyle(e).transform,
        animation:getComputedStyle(e).animationName,transition:getComputedStyle(e).transitionDuration,
        selected:getComputedStyle(document.querySelector('.doc-link.active'),'::after').animationName,
        scroll:getComputedStyle(document.documentElement).scrollBehavior})''')
    assert reduced == dict(transform='none', animation='none', transition='0s', selected='none', scroll='auto'), (theme['id'], reduced)
    page.mouse.move(0, 0)
    return {'theme': theme['id'], 'animated': theme['animated'], 'hover_animation': expected_hover,
            'selected_animation': expected_selected, 'reduced_motion': True, 'local_font_loaded': True}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--skip-static-builds', action='store_true')
    parser.add_argument('--only-new', action='store_true')
    args = parser.parse_args()
    catalog = json.loads((HERE / 'catalog.json').read_text(encoding='utf-8'))
    selected = [theme for theme in catalog['themes'] if not args.only_new or theme.get('collection') == 'expressive']
    screenshots = ROOT / '.test-output/theme-gallery'; screenshots.mkdir(parents=True, exist_ok=True)
    errors, requests, checks, contrast_results, interactions = [], [], [], [], []
    baseline_path = screenshots / 'original-theme-hashes.json'
    preserved = 0
    if baseline_path.exists():
        baseline = json.loads(baseline_path.read_text(encoding='utf-8'))
        for path, digest in baseline['css'].items():
            assert hashlib.sha256((ROOT / path).read_bytes()).hexdigest() == digest, 'An original theme was modified: ' + path
        actual = {theme['id']: theme for theme in catalog['themes']}
        assert all(actual[t['id']] == t for t in baseline['catalog_themes']), 'An original theme definition changed'
        preserved = len(baseline['css'])
    source_hashes = {str(p): hashlib.sha256(p.read_bytes()).hexdigest() for p in (ROOT / 'examples/reading-plan').rglob('*.md')}
    with tempfile.TemporaryDirectory(prefix='plan-html-theme-acceptance-') as temp:
        folder = Path(temp)
        standalone = folder / 'preview.html'
        shutil.copyfile(ROOT / 'preview.html', standalone)
        static = []
        if not args.skip_static_builds:
            # These exercise the real renderer and packager. No preview code is involved.
            for theme in selected:
                target = folder / (theme['id'] + '.html')
                result = subprocess.run([sys.executable, str(ROOT / 'scripts/plan_html.py'), 'build', str(ROOT / 'examples/reading-plan'), '--output', str(target), '--enhancements', str(ROOT / 'examples/reading-plan/enhancements.json'), '--theme', theme['id'], '--format', 'single'], capture_output=True, text=True, encoding='utf-8')
                assert result.returncode == 0, result.stderr
                page_source = target.read_text(encoding='utf-8')
                assert 'id="preview-theme-select"' not in page_source and 'data-preview-theme=' not in page_source, 'Preview selector leaked into normal skill output'
                bundle = json.loads(target.with_suffix('.bundle.json').read_text(encoding='utf-8'))
                assert bundle['self_contained_static_resources'] and not bundle['external_resources']
                static.append((theme, target))
                print('Normal standalone build:', theme['id'], flush=True)
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            context = browser.new_context(viewport={'width': 1512, 'height': 1000}, color_scheme='light', reduced_motion='reduce')
            context.route('http://**/*', lambda route: (requests.append(route.request.url), route.abort()))
            context.route('https://**/*', lambda route: (requests.append(route.request.url), route.abort()))
            page = context.new_page(); page.set_default_timeout(15000)
            page.on('pageerror', lambda error: errors.append(str(error)))
            page.on('requestfailed', lambda request: errors.append('Resource failed: ' + request.url[:100]))
            page.goto(standalone.as_uri())
            page.wait_for_selector('html[data-reader-ready="true"]', state='attached', timeout=45000)
            wait_preview(page, catalog.get('preview_default', catalog['themes'][0]['id']))
            assert page.locator('#preview-theme-select option').count() == len(catalog['themes'])
            assert page.locator('.document').count() == 4
            original_text = source_text(page)
            for theme in selected:
                page.locator('#preview-theme-select').select_option(theme['id'])
                wait_preview(page, theme['id'])
                for mode in ('light', 'dark'):
                    if page.locator('html').get_attribute('data-theme') != mode:
                        previous = page.locator('.mermaid svg').get_attribute('id')
                        page.locator('#theme-toggle').click()
                        page.wait_for_function('(previous)=>document.querySelector(".mermaid svg")?.id!==previous', arg=previous)
                    assert not page.locator('.diagram-error:not([hidden])').count(), f'Diagram failed: {theme["id"]}/{mode}'
                    assert page.locator('.mermaid svg').count() == 1
                    assert original_text == source_text(page), 'Theme changed source content'
                    values = page.evaluate('Object.fromEntries(["bg","surface","surface-2","text","muted","subtle","accent","accent-soft","code-bg","syntax-comment","syntax-keyword","syntax-string","syntax-number","syntax-name"].map(k=>[k,getComputedStyle(document.documentElement).getPropertyValue("--"+k).trim()]))')
                    pairs = [(fg, bg) for fg in ('text', 'muted', 'subtle', 'accent') for bg in ('bg', 'surface', 'surface-2', 'accent-soft')]
                    pairs += [(token, 'code-bg') for token in ('text', 'syntax-comment', 'syntax-keyword', 'syntax-string', 'syntax-number', 'syntax-name')]
                    ratios = [(fg + '/' + bg, contrast(values[fg], values[bg])) for fg, bg in pairs]
                    minimum = min(ratios, key=lambda item: item[1])
                    assert minimum[1] >= 4.5, f'Contrast {theme["id"]}/{mode} {minimum}'
                    contrast_results.append({'theme': theme['id'], 'mode': mode, 'minimum_ratio': round(minimum[1], 2), 'pair': minimum[0]})
                    page.evaluate('window.scrollTo(0,0)')
                    page.screenshot(path=str(screenshots / f'{theme["id"]}-{mode}.png'))
                    page.locator('.doc-link').nth(2).click()
                    assert 'doc-' in page.url
                    page.keyboard.press('Control+k'); page.locator('#search-input').fill('rastreabilidade')
                    assert page.locator('.search-result').count() > 0
                    page.keyboard.press('Escape')
                    page.set_viewport_size({'width': 360, 'height': 800})
                    assert page.evaluate('document.documentElement.scrollWidth <= innerWidth+1'), f'Mobile overflow: {theme["id"]}/{mode}'
                    assert page.locator('#preview-theme-select').is_visible()
                    page.set_viewport_size({'width': 1512, 'height': 1000})
                    checks.append(theme['id'] + '/' + mode)
                if theme.get('collection') == 'expressive':
                    interactions.append(interaction_state(page, theme))
                print('Preview, navigation and contrast:', theme['id'], flush=True)
            last = catalog['themes'][-1]['id']
            page.locator('#preview-next').click(); wait_preview(page, catalog['themes'][0]['id'])
            page.locator('#preview-previous').click(); wait_preview(page, last)
            page.reload(); page.wait_for_selector('html[data-reader-ready="true"]', state='attached')
            wait_preview(page, last)
            assert page.locator('html').get_attribute('data-theme') == 'dark', 'Appearance selection reset light/dark preference'
            page.locator('#preview-collapse').click()
            assert page.locator('#preview-controls').is_hidden()
            page.locator('#preview-collapse').click()
            page.locator('.code-wrap-toggle').first.click()
            page.locator('#reading-settings').click(); page.locator('#reading-size').fill('18'); page.keyboard.press('Escape')
            page.locator('#preview-theme-select').select_option('caderno'); wait_preview(page, 'caderno')
            assert page.locator('.prose').first.evaluate('e=>getComputedStyle(e).fontSize') == '18px', 'Theme reset reading preferences'
            page.emulate_media(media='print')
            assert page.locator('#theme-preview').is_hidden()
            page.emulate_media(media='screen')
            for theme, target in static:
                page.goto(target.as_uri())
                page.wait_for_selector('html[data-reader-ready="true"]', state='attached', timeout=45000)
                assert page.locator('#theme-preview').count() == 0
                assert page.locator('.mermaid svg').count() == 1
                previous_mode = page.locator('#theme-toggle').get_attribute('aria-checked')
                previous_svg = page.locator('.mermaid svg').get_attribute('id')
                page.locator('#theme-toggle').click()
                assert page.locator('#theme-toggle').get_attribute('aria-checked') != previous_mode
                page.wait_for_function('(previous)=>document.querySelector(".mermaid svg")?.id!==previous', arg=previous_svg)
            browser.close()
    assert not requests, requests
    assert not errors, errors
    assert source_hashes == {str(p): hashlib.sha256(p.read_bytes()).hexdigest() for p in (ROOT / 'examples/reading-plan').rglob('*.md')}
    # Compact contact sheets for human review; the full screenshots are kept alongside.
    for mode in ('light', 'dark'):
        sheet = Image.new('RGB', (1280, math.ceil(len(selected)/2)*396), '#dddddd')
        draw = ImageDraw.Draw(sheet)
        for index, theme in enumerate(selected):
            image = Image.open(screenshots / f'{theme["id"]}-{mode}.png').convert('RGB')
            image.thumbnail((640, 365))
            x, y = (index % 2) * 640, (index // 2) * 396
            sheet.paste(image, (x, y + 26))
            draw.text((x + 12, y + 6), f'{index+1:02d}  {theme["name"]}', fill='#202020')
        sheet.save(screenshots / (mode + '-contact-sheet.png'))
    report = {'preview_states': checks, 'normal_standalone_builds': len(static), 'preview_selector_in_normal_builds': False, 'preserved_original_css': preserved, 'network_requests': requests, 'errors': errors, 'contrast': contrast_results, 'interactions': interactions, 'screenshots': str(screenshots)}
    (screenshots / 'acceptance.json').write_text(json.dumps(report, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
