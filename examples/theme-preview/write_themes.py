#!/usr/bin/env python3
"""Write reusable CSS themes from explicit design data; no AI or network needed."""
import json
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
KEYS = ['bg', 'surface', 'surface-2', 'text', 'muted', 'subtle', 'line', 'accent', 'accent-soft', 'accent-strong', 'code-bg']
FONTS = {'source-serif-4': ('Plan Serif', [400, 600]), 'dm-sans': ('Plan DM', [400, 600, 700]), 'ibm-plex-sans': ('Plan Plex', [400, 600])}
FONTS.update({'caveat': ('Plan Caveat', [400, 700]), 'kalam': ('Plan Kalam', [400, 700]), 'cinzel': ('Plan Cinzel', [600]), 'im-fell-english': ('Plan Fell', [400]), 'bebas-neue': ('Plan Bebas', [400]), 'libre-baskerville': ('Plan Baskerville', [400, 700]), 'rajdhani': ('Plan Rajdhani', [600, 700])})


def declarations(values):
    return ''.join(f'  --{key}: {value};\n' for key, value in values.items())


def main():
    catalog = json.loads((HERE / 'catalog.json').read_text(encoding='utf-8'))
    for theme in catalog['themes']:
        css = f'/* {theme["name"]}. {theme["note"]}\n * Reference: design-inspiration-mcp / {theme["reference"]}. Adapted for this reader.\n */\n'
        for family in theme['fonts']:
            name, weights = FONTS[family]
            for weight in weights:
                css += f'@font-face {{\n  font-family: "{name}";\n  src: url("../assets/fonts/{family}-latin-{weight}-normal.woff2") format("woff2");\n  font-style: normal;\n  font-weight: {weight};\n  font-display: swap;\n}}\n'
        css += ':root {\n' + declarations(theme['appearance']) + '}\n'
        for mode in ('light', 'dark'):
            values = dict(zip(KEYS, theme[mode]))
            # All small text and syntax palettes are explicit in each mode.
            values.update({'syntax-comment': values['muted'], 'syntax-keyword': '#792b83' if mode == 'light' else '#deb1ee', 'syntax-string': '#175d39' if mode == 'light' else '#a8d4ae', 'syntax-number': '#82400e' if mode == 'light' else '#f0c192', 'syntax-name': '#20518a' if mode == 'light' else '#add0f6', 'table-stripe': values['code-bg'], 'table-hover': values['accent-soft'], 'shadow': '0 16px 55px #1c25351a' if mode == 'light' else '0 16px 55px #0005', 'panel-shadow': 'none', 'panel-bg': 'var(--surface)'})
            if theme['id'] in {'coral', 'polar', 'prisma', 'iris'}:
                values['panel-shadow'] = '0 5px 20px #24345208' if mode == 'light' else '0 5px 24px #0002'
            if theme['id'] in {'prisma', 'iris'}:
                values['panel-bg'] = f'linear-gradient(145deg, {values["surface"]}, color-mix(in srgb, {values["surface"]} 94%, {values["accent-soft"]}))'
            values.update(theme.get('effects', {}).get(mode, {}))
            css += f'html[data-theme="{mode}"] {{\n' + declarations(values) + '}\n'
        (ROOT / 'themes' / (theme['id'] + '.css')).write_text(css, encoding='utf-8', newline='\n')
    print(f'Wrote {len(catalog["themes"])} standalone CSS themes with explicit light/dark palettes.')


if __name__ == '__main__':
    main()
