"""Theme selection and a small CSS contract that keeps reader layout independent."""
from pathlib import Path
import re
import tinycss2


def resolve_theme(value, root):
    candidate = Path(value).expanduser()
    if not candidate.is_file():
        candidate = root / 'themes' / (value if value.endswith('.css') else value + '.css')
    if not candidate.is_file():
        raise ValueError(f'Theme not found: {value}. Put NAME.css in {root / "themes"} or pass a CSS path.')
    validate_theme(candidate)
    return candidate.resolve()


def validate_theme(path):
    selector = re.compile(r'(?:html|:root)(?:\[data-(?:theme|accent)\s*=\s*(?:"[\w-]+"|\'[\w-]+\'|[\w-]+)\])*')

    def visit(rules):
        for rule in rules:
            if rule.type in {'whitespace', 'comment'}:
                continue
            if rule.type == 'qualified-rule':
                selectors = tinycss2.serialize(rule.prelude).strip().split(',')
                if not all(selector.fullmatch(s.strip()) for s in selectors):
                    raise ValueError(f'Theme {path.name}: use html/:root with data-theme or data-accent selectors; layout CSS belongs in --extra-css.')
                for declaration in tinycss2.parse_declaration_list(rule.content, skip_comments=True, skip_whitespace=True):
                    if declaration.type != 'declaration' or not declaration.name.startswith('--'):
                        raise ValueError(f'Theme {path.name}: only CSS custom properties are allowed in theme selectors.')
                    if declaration.important or declaration.name in {'--header-h', '--sidebar-w', '--toc-w', '--reading-width', '--reading-font-size', '--reading-line-height', '--diagram-height'}:
                        raise ValueError(f'Theme {path.name}: geometry, reading preferences and !important belong to the reader, not the theme.')
            elif rule.type == 'at-rule' and rule.lower_at_keyword == 'font-face' and rule.content is not None:
                continue
            elif rule.type == 'at-rule' and rule.lower_at_keyword in {'media', 'supports'} and rule.content is not None:
                visit(tinycss2.parse_rule_list(rule.content))
            else:
                raise ValueError(f'Theme {path.name}: unsupported CSS rule. Use --extra-css for structural customization.')
    visit(tinycss2.parse_stylesheet(path.read_text(encoding='utf-8-sig')))
