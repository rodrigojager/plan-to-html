#!/usr/bin/env python3
"""Build the existing plan example with a demo-only selector, then package offline."""
import hashlib
import html
import json
from pathlib import Path
import subprocess
import sys

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
from bundle_html import bundle
from themes import validate_theme


def main():
    catalog = json.loads((HERE / 'catalog.json').read_text(encoding='utf-8'))
    stage = ROOT / '.test-output' / 'theme-preview' / 'work' / 'plan.html'
    output = ROOT / 'preview.html'
    subprocess.run([sys.executable, str(ROOT / 'scripts/plan_html.py'), 'build', str(ROOT / 'examples/reading-plan'), '--enhancements', str(ROOT / 'examples/reading-plan/enhancements.json'), '--output', str(stage)], check=True, capture_output=True)
    page = stage.read_text(encoding='utf-8')
    themes = []
    options = []
    default = catalog.get('preview_default', catalog['themes'][0]['id'])
    collection = None
    for index, theme in enumerate(catalog['themes']):
        path = ROOT / 'themes' / (theme['id'] + '.css')
        validate_theme(path)
        themes.append(f'<link rel="stylesheet" href="{path.as_uri()}" media="{"all" if theme["id"] == default else "not all"}" data-preview-theme="{theme["id"]}">')
        group = theme.get('collection', 'original')
        if group != collection:
            if collection is not None:
                options.append('</optgroup>')
            options.append('<optgroup label="' + ('Novos estilos' if group == 'expressive' else 'Temas anteriores') + '">')
            collection = group
        options.append(f'<option value="{theme["id"]}">{index+1:02d} · {html.escape(theme["name"])}</option>')
    options.append('</optgroup>')
    boot = "<script>try{const links=[...document.querySelectorAll('link[data-preview-theme]')],saved=localStorage.getItem('planhtml:preview-theme'),active=links.find(l=>l.dataset.previewTheme===saved)||links.find(l=>l.dataset.previewTheme===" + json.dumps(default) + ")||links[0];links.forEach(l=>l.media=l===active?'all':'not all')}catch(e){}</script>"
    page = page.replace('</head>', '\n'.join(themes) + f'\n<link rel="stylesheet" href="{(HERE / "preview.css").as_uri()}">\n' + boot + '\n</head>', 1)
    controls = ('<aside class="theme-preview" id="theme-preview" aria-label="Prévia de temas">'
        f'<div class="theme-preview-heading"><span>Prévia de temas <small id="preview-theme-position">{next(i+1 for i,t in enumerate(catalog["themes"]) if t["id"]==default)} / {len(catalog["themes"])}</small></span><div class="theme-preview-samples" aria-hidden="true"><span></span><span></span><span></span><span></span></div><button type="button" id="preview-collapse" aria-expanded="true" aria-controls="preview-controls" aria-label="Recolher seletor de temas">−</button></div>'
        '<div id="preview-controls"><div class="theme-preview-controls"><button type="button" id="preview-previous" aria-label="Tema anterior">←</button><label class="preview-label" for="preview-theme-select">Tema visual</label><select id="preview-theme-select">' + ''.join(options) + '</select><button type="button" id="preview-next" aria-label="Próximo tema">→</button></div><p class="theme-preview-note" id="preview-theme-note" aria-live="polite"></p></div></aside>')
    payload = json.dumps(catalog, ensure_ascii=False, separators=(',', ':')).replace('<', '\\u003c')
    page = page.replace('</body>', controls + '\n<script type="application/json" id="preview-theme-data">' + payload + f'</script>\n<script src="{(HERE / "preview.js").as_uri()}"></script>\n</body>', 1)
    stage.write_text(page, encoding='utf-8', newline='\n')
    packed = bundle(stage, output)
    report = json.loads(stage.with_suffix('.manifest.json').read_text(encoding='utf-8'))
    report.update(output=str(output), format='single', html_bytes=packed['html_bytes'], html_sha256=packed['output_sha256'], bundle_manifest=packed['manifest'])
    report['preview_only'] = {'selector': True, 'source': 'examples/theme-preview/build_preview.py', 'themes': [{key: theme[key] for key in ('id', 'name', 'reference')} | {'sha256': hashlib.sha256((ROOT / 'themes' / (theme['id'] + '.css')).read_bytes()).hexdigest()} for theme in catalog['themes']], 'inspiration_source': catalog['source'], 'inspiration_commit': catalog['source_commit']}
    output.with_suffix('.manifest.json').write_text(json.dumps(report, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    print(json.dumps({'output': str(output), 'theme_count': len(catalog['themes']), 'self_contained': packed['self_contained_static_resources'], 'bytes': packed['html_bytes'], 'selector_scope': 'example-only'}, indent=2))


if __name__ == '__main__':
    main()
