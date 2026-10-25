#!/usr/bin/env python3
"""Deterministic Markdown plan reader. Use scan for a compact, token-efficient outline."""
from __future__ import annotations

import argparse
import base64
import copy
from collections import Counter
from dataclasses import dataclass, field
import hashlib
import html
from html.parser import HTMLParser
import json
import math
import mimetypes
import os
from pathlib import Path
import re
import shutil
import sys
import tempfile
import unicodedata
from urllib.parse import quote, unquote, urlsplit

ROOT = Path(__file__).resolve().parents[1]
for stream in (sys.stdout, sys.stderr):
    if hasattr(stream, "reconfigure"):
        stream.reconfigure(encoding="utf-8")
sys.path.insert(0, str(ROOT / ".vendor"))
try:
    from markdown_it import MarkdownIt
    from mdit_py_plugins.footnote import footnote_plugin
    from mdit_py_plugins.tasklists import tasklists_plugin
    from mdit_py_plugins.front_matter import front_matter_plugin
    from reader_features import image_dimensions, data_image_bytes, highlighted_code
    from themes import resolve_theme
except ImportError:
    sys.exit(f'Dependencies missing. Run: python "{ROOT / "scripts" / "setup.py"}"')

IMAGE_EXTENSIONS = {".png", ".jpg", ".jpeg", ".gif", ".webp", ".avif", ".svg", ".bmp"}
SKIP_DIRS = {".git", "node_modules", ".vendor", ".venv", "__pycache__", ".test-output"}


def esc(value):
    return html.escape(str(value), quote=True)


def compact_json(value):
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"))


def json_script(value):
    return compact_json(value).replace("<", "\\u003c").replace("\u2028", "\\u2028").replace("\u2029", "\\u2029")


def digest(data):
    return hashlib.sha256(data).hexdigest()


def slug(text):
    text = unicodedata.normalize("NFC", text).lower().strip()
    text = re.sub(r"[^\w\-\s]", "", text, flags=re.UNICODE)
    return re.sub(r"\s", "-", text) or "section"


def plain(tokens):
    out = []
    for token in tokens or []:
        if token.type in {"text", "code_inline", "image"}:
            out.append(token.content)
        elif token.type in {"softbreak", "hardbreak"}:
            out.append(" ")
        elif token.children:
            out.append(plain(token.children))
    return "".join(out)


def parser():
    return (MarkdownIt("commonmark", {"html": True, "typographer": False})
            .enable(["table", "strikethrough"])
            .use(front_matter_plugin).use(footnote_plugin).use(tasklists_plugin, enabled=False))


def walk(tokens):
    for token in tokens:
        yield token
        if token.children:
            yield from walk(token.children)


def path_from_url(url, origin):
    parsed = urlsplit(url)
    if parsed.scheme or parsed.netloc or not parsed.path:
        return None
    return (origin.parent / unquote(parsed.path)).resolve()


@dataclass
class Document:
    path: Path
    relative: str = ""
    id: str = ""
    title: str = ""
    kind: str = ""
    source: str = ""
    sha256: str = ""
    tokens: list = field(default_factory=list)
    env: dict = field(default_factory=dict)
    headings: list = field(default_factory=list)
    links: list = field(default_factory=list)
    images: list = field(default_factory=list)
    tables: list = field(default_factory=list)
    excerpt: str = ""
    words: int = 0
    tasks: dict = field(default_factory=dict)


class RawReferences(HTMLParser):
    def __init__(self):
        super().__init__()
        self.links = []
        self.images = []

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        if tag == "a" and attrs.get("href"):
            self.links.append(attrs["href"])
        if tag == "img" and attrs.get("src"):
            self.images.append({"src": attrs["src"], "alt": attrs.get("alt", "")})


def read_document(path):
    data = path.read_bytes()
    doc = Document(path=path, source=data.decode("utf-8-sig"), sha256=digest(data))
    md = parser()
    doc.tokens = md.parse(doc.source, doc.env)
    counts = Counter()
    for index, token in enumerate(doc.tokens):
        if token.type == "heading_open":
            title = plain(doc.tokens[index + 1].children)
            base = slug(title)
            number = counts[base]
            counts[base] += 1
            anchor = base + (f"-{number}" if number else "")
            doc.headings.append({"text": title, "level": int(token.tag[1]), "anchor": anchor,
                                 "line": (token.map or [0])[0] + 1, "token_index": index})
            if token.tag == "h1" and not doc.title:
                doc.title = title
        elif token.type == "paragraph_open" and not doc.excerpt:
            content = plain(doc.tokens[index + 1].children)
            if not re.match(r"^(Kind:|Part of\s|Parte de\s|Tipo:)", content, re.I):
                doc.excerpt = content[:240]
    doc.title = doc.title or path.stem.replace("-", " ")
    for token in walk(doc.tokens):
        if token.type == "link_open":
            doc.links.append(token.attrGet("href") or "")
        elif token.type == "image":
            doc.images.append({"src": token.attrGet("src") or "", "alt": plain(token.children) or token.content})
        elif token.type in {"html_inline", "html_block"}:
            raw = RawReferences()
            raw.feed(token.content)
            doc.links.extend(raw.links)
            doc.images.extend(raw.images)
    for link in doc.links:
        if Path(unquote(urlsplit(link).path)).suffix.lower() in IMAGE_EXTENSIONS:
            if not any(image["src"] == link for image in doc.images):
                doc.images.append({"src": link, "alt": Path(unquote(urlsplit(link).path)).stem})
    kind = re.search(r"^(?:Kind|Tipo):\s*([^\n.]+)", doc.source, re.M | re.I)
    doc.kind = kind.group(1).strip() if kind else ("plan" if path.name.lower() == "plan.md" else "document")
    doc.words = sum(len(re.findall(r"\w+", plain(t.children))) for t in doc.tokens if t.type == "inline")
    tasks = [token.content for token in walk(doc.tokens) if token.type == "html_inline" and 'class="task-list-item-checkbox"' in token.content]
    doc.tasks = {"total": len(tasks), "checked": sum('checked="checked"' in task for task in tasks)}
    doc.tables = extract_tables(doc)
    return doc


def extract_tables(doc):
    tables, rows, row, cell = [], [], [], None
    section = None
    for index, token in enumerate(doc.tokens):
        if token.type == "heading_open":
            section = next(h["anchor"] for h in doc.headings if h["token_index"] == index)
        if token.type == "table_open":
            rows = []
            table = {"anchor": section, "line": (token.map or [0])[0] + 1}
        elif token.type == "tr_open":
            row = []
        elif token.type in {"td_open", "th_open"}:
            cell = ""
        elif token.type == "inline" and cell is not None:
            cell += plain(token.children)
        elif token.type in {"td_close", "th_close"}:
            row.append(cell)
            cell = None
        elif token.type == "tr_close":
            rows.append(row)
        elif token.type == "table_close":
            table.update({"headers": rows[0] if rows else [], "rows": rows[1:]})
            tables.append(table)
    return tables


def discover(inputs, explicit=False):
    seeds = []
    for value in inputs:
        path = Path(value).expanduser().resolve()
        if not path.exists():
            raise ValueError(f"Input not found: {path}")
        if path.is_dir():
            found = [p.resolve() for p in path.rglob("*") if p.suffix.lower() in {".md", ".markdown"}
                     and not any(part in SKIP_DIRS for part in p.relative_to(path).parts)]
            found.sort(key=lambda p: (p.name.lower() != "plan.md", str(p).lower()))
            seeds.extend(found)
        elif path.suffix.lower() in {".md", ".markdown"}:
            seeds.append(path)
        else:
            raise ValueError(f"Not a Markdown input: {path}")
    if not seeds:
        raise ValueError("No Markdown documents found")
    root = Path(os.path.commonpath([str(p.parent) for p in seeds]))
    # PLAN.md declares the plan boundary, so unrelated repository files stay outside.
    if len(inputs) == 1 and Path(inputs[0]).is_file() and seeds[0].name.lower() == "plan.md" and not explicit:
        root = seeds[0].parent
        rest = [p.resolve() for p in root.rglob("*") if p.suffix.lower() in {".md", ".markdown"}
                and not any(part in SKIP_DIRS for part in p.relative_to(root).parts)]
        seeds += sorted(rest, key=lambda p: str(p).lower())
    allowed = set(seeds)
    docs = {}
    ordered = []

    def ordered_links(doc):
        # to-plan's Parts section establishes reading order; earlier citations do not.
        preferred = []
        in_parts = False
        parts_level = 0
        for index, token in enumerate(doc.tokens):
            if token.type == "heading_open":
                text = plain(doc.tokens[index + 1].children).strip().lower()
                level = int(token.tag[1])
                if text in {"parts", "partes"}:
                    in_parts, parts_level = True, level
                elif in_parts and level <= parts_level:
                    in_parts = False
            if in_parts:
                preferred.extend(t.attrGet("href") for t in walk([token]) if t.type == "link_open")
        return list(dict.fromkeys(preferred + doc.links))

    # Iterative DFS handles large plans without a recursion-depth ceiling.
    pending = list(reversed(seeds))
    while pending:
        path = pending.pop()
        if path in docs:
            continue
        doc = read_document(path)
        docs[path] = doc
        ordered.append(doc)
        if not explicit:
            for link in reversed(ordered_links(doc)):
                target = path_from_url(link, path)
                if target in allowed and target not in docs:
                    pending.append(target)
    for doc in ordered:
        doc.relative = doc.path.relative_to(root).as_posix()
        doc.id = "doc-" + slug(doc.path.stem) + "-" + digest(doc.relative.encode())[:7]
        for heading in doc.headings:
            heading["id"] = f'{doc.id}--{heading["anchor"]}'
            heading["ref"] = f'{doc.relative}#{heading["anchor"]}'
    return root, ordered


class Assets:
    def __init__(self, mode="embed", output=None):
        self.mode, self.output = mode, output
        self.records = {}
        self.warnings = []
        self.dimensions = {}

    def dimensions_html(self, url, origin):
        key = (url, str(origin))
        if key not in self.dimensions:
            values = {}
            try:
                if url.startswith('data:image/'):
                    values = image_dimensions(data_image_bytes(url))
                else:
                    path = path_from_url(url, origin)
                    if path and path.is_file():
                        values = image_dimensions(path.read_bytes())
            except (ValueError, OSError):
                pass
            self.dimensions[key] = values
        return ''.join(f' {key}="{value}"' for key, value in self.dimensions[key].items())

    def image(self, url, origin):
        if url.startswith("data:image/"):
            return url
        parsed = urlsplit(url)
        if parsed.scheme in {"https", "http"}:
            self.records.setdefault(url, {"source": url, "remote": True})
            return url
        path = path_from_url(url, origin)
        if path is None or not path.is_file():
            message = f"Missing image: {url} (from {origin.name})"
            if message not in self.warnings:
                self.warnings.append(message)
            return None
        data = path.read_bytes()
        mime = mimetypes.guess_type(path.name)[0] or "application/octet-stream"
        if not mime.startswith("image/"):
            self.warnings.append(f"Unsupported image: {path.name}")
            return None
        sha = digest(data)
        self.records.setdefault(str(path), {"source": str(path), "sha256": sha, "bytes": len(data), "remote": False})
        if self.mode == "copy" and self.output:
            folder = self.output.parent / (self.output.stem + "-assets")
            folder.mkdir(parents=True, exist_ok=True)
            target = folder / (sha[:16] + path.suffix.lower())
            target.write_bytes(data)
            return quote(folder.name) + "/" + quote(target.name)
        return f"data:{mime};base64," + base64.b64encode(data).decode()


class CleanHTML(HTMLParser):
    ALLOWED = {"a", "abbr", "b", "blockquote", "br", "caption", "code", "dd", "del", "details", "div", "dl", "dt", "em",
               "figcaption", "figure", "h1", "h2", "h3", "h4", "h5", "h6", "hr", "i", "img", "input", "kbd", "li", "mark", "ol", "p", "pre", "s", "small", "span", "strong", "sub", "summary", "sup", "table", "tbody", "td", "th", "thead", "tr", "ul"}
    VOID = {"br", "hr", "img", "input"}

    def __init__(self, context, doc):
        super().__init__(convert_charrefs=False)
        self.context, self.doc, self.output = context, doc, []
        self.blocked = 0

    def handle_starttag(self, tag, attrs):
        if tag in {"script", "style", "iframe", "object"}:
            self.blocked += 1
        if self.blocked or tag not in self.ALLOWED:
            return
        attrs = dict(attrs)
        safe = {}
        for key in ("title", "alt", "colspan", "rowspan", "open"):
            if key in attrs:
                safe[key] = attrs[key] or ""
        if tag == "input":
            if attrs.get("type") != "checkbox":
                return
            safe.update({"type": "checkbox", "disabled": "", "aria-label": "Source checklist"})
            for key in ("checked", "class"):
                if key in attrs:
                    safe[key] = attrs[key] or ""
        if tag == "a" and "href" in attrs:
            safe["href"] = self.context.link(attrs["href"], self.doc)
        if tag == "img":
            image = self.context.assets.image(attrs.get("src", ""), self.doc.path)
            if not image:
                self.output.append(f'<span class="missing-asset">{esc(attrs.get("alt") or attrs.get("src", "Image"))}</span>')
                return
            safe.update({"src": image, "loading": "lazy", "class": "zoomable", "tabindex": "0"})
            # Read intrinsic dimensions from the original bytes; never resample images.
            dimensions = self.context.assets.dimensions_html(attrs.get('src', ''), self.doc.path)
            for key, value in re.findall(r' (width|height)="(\d+)"', dimensions):
                safe[key] = value
        self.output.append("<" + tag + "".join(f' {key}="{esc(value)}"' for key, value in safe.items()) + ">")

    def handle_startendtag(self, tag, attrs):
        self.handle_starttag(tag, attrs)
        if tag not in self.VOID:
            self.handle_endtag(tag)

    def handle_endtag(self, tag):
        if tag in {"script", "style", "iframe", "object"} and self.blocked:
            self.blocked -= 1
            return
        if not self.blocked and tag in self.ALLOWED and tag not in self.VOID:
            self.output.append(f"</{tag}>")

    def handle_data(self, data):
        if not self.blocked:
            self.output.append(esc(data))

    def handle_entityref(self, name):
        if not self.blocked:
            self.output.append(f"&{name};")

    def handle_charref(self, name):
        if not self.blocked:
            self.output.append(f"&#{name};")


class Context:
    def __init__(self, root, docs, assets, language):
        self.root, self.docs, self.assets, self.language = root, docs, assets, language
        self.by_path = {doc.path: doc for doc in docs}
        self.warnings = []
        self.mermaid = False
        self.enhancements = {}
        self.locale = LABELS[language]

    def ref(self, reference):
        parsed = urlsplit(reference)
        if parsed.scheme or parsed.netloc:
            raise ValueError(f"Expected a local source reference: {reference}")
        path = (self.root / unquote(parsed.path)).resolve()
        doc = self.by_path.get(path)
        if not doc:
            raise ValueError(f"Unknown source document: {reference}")
        if parsed.fragment:
            anchor = unquote(parsed.fragment)
            heading = next((h for h in doc.headings if h["anchor"] == anchor), None)
            if not heading:
                raise ValueError(f"Unknown source heading: {reference}")
            return doc, heading["id"], heading
        return doc, doc.id, None

    def link(self, url, doc):
        parsed = urlsplit(url)
        if parsed.scheme and parsed.scheme.lower() not in {"http", "https", "mailto", "tel"}:
            return "#"
        if not parsed.path and parsed.fragment:
            anchor = unquote(parsed.fragment)
            heading = next((h for h in doc.headings if h["anchor"] == anchor), None)
            if heading:
                return "#" + heading["id"]
            # Footnote anchors are namespaced separately by the footnote renderer.
            self.warnings.append(f"Unresolved fragment: {url} ({doc.relative})")
            return "#" + doc.id
        target = path_from_url(url, doc.path)
        if target in self.by_path:
            other = self.by_path[target]
            if parsed.fragment:
                heading = next((h for h in other.headings if h["anchor"] == unquote(parsed.fragment)), None)
                if heading:
                    return "#" + heading["id"]
                self.warnings.append(f"Unresolved fragment: {url} ({doc.relative})")
            return "#" + other.id
        if target and target.suffix.lower() in {".md", ".markdown"}:
            self.warnings.append(f"Markdown link outside selected plan: {url} ({doc.relative})")
        if target and not target.exists():
            self.warnings.append(f"Missing local link: {url} ({doc.relative})")
        if target and self.assets.output:
            try:
                return quote(os.path.relpath(target, self.assets.output.parent).replace(os.sep, "/"), safe="/:#")
            except ValueError:
                return target.as_uri()
        return url

    def source_chips(self, refs):
        out = []
        for reference in refs:
            doc, anchor, heading = self.ref(reference)
            label = heading["text"] if heading else doc.title
            out.append(f'<a class="source-chip" href="#{anchor}">{esc(label)}</a>')
        return '<div class="visual-sources"><span>' + self.locale["sources"] + '</span>' + "".join(out) + "</div>"

    def image_figure(self, src, alt, origin, caption=True):
        resolved = self.assets.image(src, origin)
        if not resolved:
            return f'<span class="missing-asset" role="note">{esc(self.locale["missing_image"])}: {esc(src)}</span>'
        return (f'<figure class="reference-image"><img class="zoomable" tabindex="0" src="{esc(resolved)}" alt="{esc(alt)}" loading="lazy"{self.assets.dimensions_html(src, origin)}>'
                + (f'<figcaption>{esc(alt)}</figcaption>' if caption and alt else "") + "</figure>")


LABELS = {
    "pt": {"brand": "Caderno de plano", "search": "Buscar no plano", "documents": "Documentos", "sections": "seções", "references": "referências", "read": "min de leitura", "overview": "Visão geral", "reading_map": "Mapa de leitura", "reading_map_hint": "As conexões mostram os links entre os documentos.", "source": "Fonte", "sources": "Fontes", "toc": "Nesta página", "theme": "Alternar modo claro e escuro", "menu": "Abrir navegação", "focus": "Modo de foco", "print": "Imprimir ou salvar PDF", "close": "Fechar", "search_hint": "Busque por um assunto, decisão ou detalhe…", "no_results": "Nenhum resultado encontrado.", "search_start": "Digite para buscar em todos os documentos.", "copy": "Copiar código", "copied": "Copiado", "missing_image": "Imagem indisponível", "gallery": "Referências visuais", "gallery_hint": "Amplie uma imagem para explorar os detalhes.", "start": "Começar a leitura", "top": "Voltar ao início", "diagram_error": "Não foi possível desenhar este diagrama. O código original está disponível.", "diagram_code": "Ver código do diagrama", "reading": "Leitura", "navigation": "Navegação do plano", "source_note": "Conteúdo integrado dos arquivos Markdown", "document_unit": "documentos", "section_unit": "seções", "reference_unit": "imagens", "skip": "Pular para o conteúdo", "done": "Fim do plano", "done_hint": "Volte a uma seção pelo menu ou use a busca para encontrar um detalhe.", "remote": "Imagem externa", "chart": "Gráfico", "download": "Baixar imagem"},
    "en": {"brand": "Plan notebook", "search": "Search this plan", "documents": "Documents", "sections": "sections", "references": "references", "read": "min read", "overview": "Overview", "reading_map": "Reading map", "reading_map_hint": "Connections show the links between documents.", "source": "Source", "sources": "Sources", "toc": "On this page", "theme": "Toggle light and dark mode", "menu": "Open navigation", "focus": "Focus mode", "print": "Print or save PDF", "close": "Close", "search_hint": "Find a topic, decision, or detail…", "no_results": "No results found.", "search_start": "Type to search across all documents.", "copy": "Copy code", "copied": "Copied", "missing_image": "Image unavailable", "gallery": "Visual references", "gallery_hint": "Enlarge an image to explore the details.", "start": "Start reading", "top": "Back to top", "diagram_error": "This diagram could not be rendered. Its original code is available.", "diagram_code": "View diagram code", "reading": "Reading", "navigation": "Plan navigation", "source_note": "Content integrated from Markdown sources", "document_unit": "documents", "section_unit": "sections", "reference_unit": "images", "skip": "Skip to content", "done": "End of plan", "done_hint": "Return to a section using the navigation or search for a detail.", "remote": "Remote image", "chart": "Chart", "download": "Download image"}
}

LABELS['pt'].update({'settings': 'Ajustes de leitura', 'font_size': 'Tamanho do texto', 'line_height': 'Espaçamento entre linhas', 'width': 'Largura da leitura', 'narrow': 'Estreita', 'standard': 'Padrão', 'wide': 'Ampla', 'reset': 'Restaurar padrão', 'copy_link': 'Copiar link da seção', 'wrap': 'Quebrar linhas', 'line_numbers': 'Números de linha', 'zoom_in': 'Aproximar', 'zoom_out': 'Afastar', 'fit': 'Ajustar', 'expand': 'Ampliar diagrama', 'diagram_controls': 'Controles do diagrama', 'diagram_help': 'Arraste para mover. Teclado: setas, +, − e 0 para ajustar.'})
LABELS['en'].update({'settings': 'Reading settings', 'font_size': 'Text size', 'line_height': 'Line spacing', 'width': 'Reading width', 'narrow': 'Narrow', 'standard': 'Standard', 'wide': 'Wide', 'reset': 'Reset defaults', 'copy_link': 'Copy section link', 'wrap': 'Wrap lines', 'line_numbers': 'Line numbers', 'zoom_in': 'Zoom in', 'zoom_out': 'Zoom out', 'fit': 'Fit', 'expand': 'Expand diagram', 'diagram_controls': 'Diagram controls', 'diagram_help': 'Drag to pan. Keyboard: arrows, +, − and 0 to fit.'})
LABELS['pt'].update({'map_focus_hint': 'Passe o mouse, use o teclado ou fixe um documento para ver as ligações.', 'map_show_all': 'Mostrar todos', 'map_pin': 'Fixar relações', 'map_collapse': 'Recolher mapa'})
LABELS['en'].update({'map_focus_hint': 'Hover, use the keyboard or pin a document to see its links.', 'map_show_all': 'Show all', 'map_pin': 'Pin connections', 'map_collapse': 'Collapse map'})


def diagram_markup(code, context):
    context.mermaid = True
    l = context.locale
    toolbar = ('<div class="diagram-toolbar" role="group" aria-label="' + esc(l['diagram_controls']) + '">'
               + ''.join(f'<button type="button" data-diagram-action="{action}" aria-label="{esc(l[label])}" title="{esc(l[label])}">{text}</button>' for action, label, text in [('out', 'zoom_out', '−'), ('in', 'zoom_in', '+'), ('fit', 'fit', esc(l['fit'])), ('expand', 'expand', '⛶')])
               + '<output class="diagram-scale" aria-live="polite">100%</output></div>')
    return ('<div class="diagram-wrap"><div class="diagram-viewer">' + toolbar
            + '<div class="diagram-viewport" tabindex="0" role="region" aria-label="' + esc(l['diagram_help']) + '"><div class="mermaid" data-diagram-source="' + esc(code) + '"></div></div></div>'
            f'<p class="diagram-error" role="status" hidden>{esc(context.locale["diagram_error"])}</p>'
            f'<details class="diagram-source"><summary>{esc(context.locale["diagram_code"])}</summary><pre><code>{esc(code)}</code></pre></details></div>')


def renderer(context, doc):
    md = parser()

    def image_rule(self, tokens, idx, options, env):
        token = tokens[idx]
        # Inline-safe span avoids invalid figure-inside-paragraph markup.
        src, alt = token.attrGet("src") or "", plain(token.children) or token.content
        resolved = context.assets.image(src, doc.path)
        if not resolved:
            return f'<span class="missing-asset">{esc(context.locale["missing_image"])}: {esc(src)}</span>'
        return f'<span class="inline-image"><img class="zoomable" tabindex="0" src="{esc(resolved)}" alt="{esc(alt)}" loading="lazy"{context.assets.dimensions_html(src, doc.path)}><span class="image-caption">{esc(alt)}</span></span>'

    def link_rule(self, tokens, idx, options, env):
        token = tokens[idx]
        original = token.attrGet("href") or ""
        token.attrSet("href", context.link(original, doc))
        if urlsplit(original).scheme in {"http", "https"}:
            token.attrSet("rel", "noopener noreferrer")
        return self.renderToken(tokens, idx, options, env)

    def fence_rule(self, tokens, idx, options, env):
        token = tokens[idx]
        language = token.info.strip().split()[0] if token.info.strip() else "text"
        if language == "mermaid":
            return diagram_markup(token.content, context)
        l = context.locale
        return (f'<div class="code-block"><div class="code-toolbar"><span>{esc(language)}</span><div class="code-actions">'
                f'<button class="code-lines-toggle" type="button" aria-pressed="true" aria-label="{esc(l["line_numbers"])}" title="{esc(l["line_numbers"])}">#</button>'
                f'<button class="code-wrap-toggle" type="button" aria-pressed="false" aria-label="{esc(l["wrap"])}" title="{esc(l["wrap"])}">↵</button>'
                f'<button class="copy-code" type="button">{esc(l["copy"])}</button></div></div>'
                f'<pre><code class="language-{esc(language)}">{highlighted_code(token.content, language)}</code></pre></div>')

    def raw_rule(self, tokens, idx, options, env):
        cleaner = CleanHTML(context, doc)
        cleaner.feed(tokens[idx].content)
        return "".join(cleaner.output)

    def heading_rule(self, tokens, idx, options, env):
        result = self.renderToken(tokens, idx, options, env)
        previous = tokens[idx - 2]
        if not (previous.tag == 'h1' and doc.headings and previous.attrGet('id') == doc.headings[0]['id']):
            result = (f'<button class="heading-anchor" type="button" data-anchor="{esc(previous.attrGet("id"))}" aria-label="{esc(context.locale["copy_link"])}" title="{esc(context.locale["copy_link"])}"><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.7" aria-hidden="true"><path d="M10 13a5 5 0 0 0 7 0l3-3a5 5 0 0 0-7-7l-2 2M14 11a5 5 0 0 0-7 0l-3 3a5 5 0 0 0 7 7l2-2"/></svg></button>' + result)
        return result + context.enhancements.get(previous.attrGet("id"), "")

    def table_open(self, tokens, idx, options, env):
        return '<div class="table-wrap" tabindex="0" role="region" aria-label="' + esc(doc.title) + '">' + self.renderToken(tokens, idx, options, env)

    def table_close(self, tokens, idx, options, env):
        return self.renderToken(tokens, idx, options, env) + "</div>"

    def footnote_anchor_name(self, tokens, idx, options, env):
        return doc.id + "-" + str(tokens[idx].meta["id"] + 1)

    md.add_render_rule("image", image_rule)
    md.add_render_rule("link_open", link_rule)
    md.add_render_rule("fence", fence_rule)
    md.add_render_rule("html_block", raw_rule)
    md.add_render_rule("html_inline", raw_rule)
    md.add_render_rule("heading_close", heading_rule)
    md.add_render_rule("table_open", table_open)
    md.add_render_rule("table_close", table_close)
    md.add_render_rule("footnote_anchor_name", footnote_anchor_name)
    return md


def number(value, fmt):
    match = re.fullmatch(r"\s*([^\d+\-]*)([+\-]?(?:\d[\d.,\s]*\d|\d))(\s*[^\d]*)", value)
    if not match:
        raise ValueError(f"Chart cell must contain one number: {value!r}")
    raw = match.group(2).replace(" ", "").replace("\u00a0", "")
    raw = raw.replace(".", "").replace(",", ".") if fmt == "pt" else raw.replace(",", "")
    result = float(raw)
    if not math.isfinite(result):
        raise ValueError("Chart values must be finite")
    return result


def component_markup(component, context):
    sources = component.get("sources", [])
    if not isinstance(sources, list) or not sources:
        raise ValueError("Every visual component requires source references")
    source_doc, _, source_heading = context.ref(sources[0])
    title = component.get("title") or (source_heading["text"] if source_heading else source_doc.title)
    chips = context.source_chips(sources)
    kind = component.get("type")
    if kind == "mermaid":
        code = component["code"]
        if "%%{init" in code or re.search(r"^\s*click\s", code, re.M):
            raise ValueError("Mermaid initialization and click directives are not supported")
        body = diagram_markup(code, context)
    elif kind == "timeline":
        items = []
        for i, item in enumerate(component["items"]):
            _, anchor, _ = context.ref(item["ref"])
            items.append(f'<li><span class="step-number">{i+1:02d}</span><div><a href="#{anchor}">{esc(item["label"])}</a>'
                         + (f'<p>{esc(item["detail"])}</p>' if item.get("detail") else "") + "</div></li>")
        body = '<ol class="timeline">' + "".join(items) + "</ol>"
    elif kind == "table-chart":
        doc, _, heading = context.ref(component["table"])
        tables = [table for table in doc.tables if not heading or table["anchor"] == heading["anchor"]]
        try:
            table = tables[component.get("table_index", 0)]
            values = [(row[component.get("label_column", 0)], row[component.get("value_column", 1)]) for row in table["rows"]]
        except (IndexError, TypeError):
            raise ValueError(f"Chart table or column not found: {component['table']}") from None
        values = [(label, raw, number(raw, component.get("number_format", "en"))) for label, raw in values]
        if not values:
            raise ValueError("Cannot chart an empty table")
        low = min(0, min(item[2] for item in values))
        high = max(0, max(item[2] for item in values))
        span = high - low or 1
        zero = -low / span * 100
        bars = []
        for label, raw, numeric in values:
            start, width = min(zero, (numeric-low)/span*100), abs(numeric)/span*100
            bars.append(f'<div class="chart-row"><span class="chart-label">{esc(label)}</span><span class="bar-track" aria-hidden="true" style="--zero:{zero:.4f}%"><span class="bar-fill" style="left:{start:.4f}%;width:{width:.4f}%"></span></span><strong>{esc(raw)}</strong></div>')
        body = '<div class="bar-chart" role="group" aria-label="' + esc(title) + '">' + "".join(bars) + "</div>"
        if component.get("unit"):
            body += '<p class="chart-unit">' + esc(component["unit"]) + "</p>"
    elif kind == "image":
        body = context.image_figure(component["src"], component.get("alt", title), context.root / "PLAN.md")
    else:
        raise ValueError(f"Unknown component type: {kind}")
    return f'<aside class="enhancement" id="visual-{esc(component["id"])}"><div class="visual-heading"><span class="eyebrow">{esc(context.locale["overview"])}</span><h3>{esc(title)}</h3></div>{body}{chips}</aside>'


def load_enhancements(path, context):
    if not path:
        return {}
    specification = json.loads(Path(path).read_text(encoding="utf-8-sig"))
    if not isinstance(specification, dict):
        raise ValueError("enhancements.json must be an object")
    unsupported = set(specification) - {"version", "components"}
    if unsupported:
        raise ValueError("Unsupported document-level fields: " + ", ".join(sorted(unsupported))
                         + ". The title comes from Markdown; added introductory copy is not supported.")
    if specification.get("version") != 1:
        raise ValueError("enhancements.json requires version: 1")
    used = set()
    for component in specification.get("components", []):
        identifier = component.get("id", "")
        if not re.fullmatch(r"[a-z][a-z0-9-]*", identifier) or identifier in used:
            raise ValueError(f"Visual id must be unique and kebab-case: {identifier}")
        used.add(identifier)
        after = component.get("after", "overview")
        key = "overview" if after == "overview" else context.ref(after)[1]
        context.enhancements[key] = context.enhancements.get(key, "") + component_markup(component, context)
    return specification


def graph_data(docs, by_path):
    edges = set()
    for doc in docs:
        for url in doc.links:
            target = path_from_url(url, doc.path)
            if target in by_path and by_path[target].id != doc.id:
                edges.add((doc.id, by_path[target].id))
    return {"nodes": [{"id": doc.id, "title": doc.title, "kind": doc.kind} for doc in docs],
            "edges": [list(edge) for edge in sorted(edges)]}


def scan(root, docs, assets_dirs):
    outline = {"version": 1, "root": str(root), "documents": [], "reference_files": []}
    def compact_url(url):
        if url.startswith("data:"):
            return url.split(",", 1)[0] + f",[embedded payload: {len(url)} characters]"
        return url
    for doc in docs:
        outline["documents"].append({"path": doc.relative, "title": doc.title, "kind": doc.kind, "sha256": doc.sha256,
            "excerpt": doc.excerpt, "words": doc.words, "tasks": doc.tasks,
            "headings": [{key: value for key, value in h.items() if key not in {"token_index", "id", "anchor"}} for h in doc.headings],
            "tables": [{"ref": doc.relative + ("#"+t["anchor"] if t["anchor"] else ""), "headers": t["headers"], "rows": len(t["rows"])} for t in doc.tables],
            "images": [{"src": compact_url(image["src"]), "alt": image["alt"]} for image in doc.images],
            "links": [compact_url(url) for url in dict.fromkeys(doc.links)]})
    for folder in assets_dirs:
        outline["reference_files"].extend(str(p) for p in additional_images(folder))
    outline["reading_map"] = graph_data(docs, {doc.path: doc for doc in docs})
    return outline


def additional_images(folder):
    path = Path(folder).expanduser().resolve()
    if not path.exists():
        raise ValueError(f"Reference folder not found: {path}")
    if path.is_file():
        return [path] if path.suffix.lower() in IMAGE_EXTENSIONS else []
    return sorted((p for p in path.rglob("*") if p.suffix.lower() in IMAGE_EXTENSIONS
                   and not any(part in SKIP_DIRS for part in p.relative_to(path).parts)), key=lambda p: str(p).lower())


def gallery(context, folders):
    images = []
    seen = set()
    for doc in context.docs:
        for image in doc.images:
            key = str(path_from_url(image["src"], doc.path) or image["src"])
            if key not in seen:
                seen.add(key)
                images.append((image["src"], image["alt"], doc.path, doc.id))
    for folder in folders:
        for path in additional_images(folder):
            if str(path) not in seen:
                seen.add(str(path))
                images.append((quote(path.name), path.stem.replace("-", " "), path, None))
    cards = []
    for src, alt, origin, anchor in images:
        figure = context.image_figure(src, alt, origin)
        cards.append('<div class="gallery-card">' + figure + (f'<a class="gallery-source" href="#{anchor}">{esc(context.locale["source"])}</a>' if anchor else "") + "</div>")
    return (f'<section class="gallery" id="references"><div class="section-heading"><div><span class="eyebrow">{esc(context.locale["references"])}</span><h2>{esc(context.locale["gallery"])}</h2></div><p>{esc(context.locale["gallery_hint"])}</p></div><div class="gallery-grid">' + "".join(cards) + "</div></section>") if cards else ""


def render_document(context, doc, number_):
    md = renderer(context, doc)
    for heading in doc.headings:
        token = doc.tokens[heading["token_index"]]
        token.attrSet("id", heading["id"])
        token.attrSet("data-section", "")
    body = md.renderer.render(doc.tokens, md.options, doc.env)
    # First H1 is represented by the article header; leave its anchor accessible.
    first = next((h for h in doc.headings if h["level"] == 1), None)
    if first:
        opening = f'<h1 id="{first["id"]}" data-section="">'
        body = body.replace(opening, f'<h1 class="source-title" id="{first["id"]}" data-section="">', 1)
    refs = []
    for image in doc.images:
        # Linked image references receive a preview even if they were not inline images.
        if any(token.type == "image" and token.attrGet("src") == image["src"] for token in walk(doc.tokens)):
            continue
        if re.search(r'<img\b[^>]*\bsrc\s*=\s*["\']' + re.escape(image["src"]), doc.source, re.I):
            continue
        refs.append(context.image_figure(image["src"], image["alt"], doc.path))
    return (f'<article class="document" id="{doc.id}" data-doc-id="{doc.id}"><header class="document-header"><div class="document-meta"><span class="chapter-number">{number_:02d}</span><span class="kind">{esc(doc.kind)}</span><span>{max(1, math.ceil(doc.words/220))} {esc(context.locale["read"])}</span></div><h2>{esc(doc.title)}</h2><div class="source-label">{esc(context.locale["source"])} <code>{esc(doc.relative)}</code></div></header>'
            + context.enhancements.get(doc.id, "") + '<div class="prose">' + body + "".join(refs) + "</div></article>")


def icon(name):
    paths = {"search": '<circle cx="10.5" cy="10.5" r="6.5"/><path d="m16 16 4.5 4.5"/>',
             "sun": '<circle cx="12" cy="12" r="4"/><path d="M12 2v2m0 16v2M2 12h2m16 0h2M5 5l1.4 1.4m11.2 11.2L19 19M5 19l1.4-1.4M17.6 6.4 19 5"/>',
             "moon": '<path d="M20 14.1A8.4 8.4 0 0 1 9.9 4a8.5 8.5 0 1 0 10.2 10.1Z"/>',
             "menu": '<path d="M4 6h16M4 12h16M4 18h16"/>',
             "focus": '<path d="M8 3H3v5m13-5h5v5M3 16v5h5m13-5v5h-5"/>',
             "print": '<path d="M6 9V3h12v6M6 17H3V9h18v8h-3M6 14h12v7H6z"/>',
             "arrow": '<path d="M5 12h14m-5-5 5 5-5 5"/>',
             "close": '<path d="m6 6 12 12M6 18 18 6"/>',
             "book": '<path d="M12 5c-3-2-6-2-10 0v15c4-2 7-2 10 0m0-15c3-2 6-2 10 0v15c-4-2-7-2-10 0m0-15v15"/>'}
    return '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">' + paths[name] + "</svg>"


def build_directory(args, root, docs):
    theme = resolve_theme(args.theme, ROOT)
    output = Path(args.output).expanduser().resolve()
    output.parent.mkdir(parents=True, exist_ok=True)
    if output.suffix.lower() not in {".html", ".htm"}:
        raise ValueError("Build output must have an .html extension")
    assets = Assets(args.asset_mode or "copy", output)
    context = Context(root, docs, assets, args.lang)
    load_enhancements(args.enhancements, context)
    l = context.locale
    title = docs[0].title
    nav = "".join(f'<a class="doc-link" href="#{doc.id}" data-nav-doc="{doc.id}"><span class="nav-number">{i+1:02d}</span><span>{esc(doc.title)}<small>{esc(doc.kind)}</small></span></a>' for i, doc in enumerate(docs))
    articles = "".join(render_document(context, doc, i+1) for i, doc in enumerate(docs))
    gallery_html = gallery(context, args.assets)
    images = len(assets.records)
    section_count = sum(len(doc.headings) for doc in docs)
    resource_dir = output.parent / (output.stem + "-assets")
    resource_dir.mkdir(parents=True, exist_ok=True)

    def resource_href(path):
        path = path.resolve()
        if not path.is_file():
            raise ValueError(f"Resource not found: {path}")
        try:
            return quote(os.path.relpath(path, output.parent).replace(os.sep, "/"), safe="/")
        except ValueError:
            return path.as_uri()

    def copy_resource(name, source):
        target = resource_dir / name
        target.parent.mkdir(parents=True, exist_ok=True)
        if source.resolve() != target.resolve():
            target.write_bytes(source.read_bytes())
        return resource_href(target)

    stylesheets = [f'<link rel="stylesheet" href="{esc(copy_resource("reader.css", ROOT / "assets" / "reader.css"))}">']
    for folder in ('styles', 'fonts'):
        for path in sorted((ROOT / 'assets' / folder).rglob('*')):
            if path.is_file():
                copy_resource(folder + '/' + path.relative_to(ROOT / 'assets' / folder).as_posix(), path)
    if not (ROOT / 'assets' / 'fonts' / 'inter-latin-400-normal.woff2').is_file():
        raise ValueError('Embedded fonts missing. Run scripts/setup.py.')
    stylesheets.append(f'<link rel="stylesheet" href="{esc(copy_resource("theme-default.css", ROOT / "themes" / "default.css"))}">')
    if theme != (ROOT / 'themes' / 'default.css').resolve():
        stylesheets.append(f'<link rel="stylesheet" href="{esc(resource_href(theme))}">')
    if args.extra_css:
        stylesheets.append(f'<link rel="stylesheet" href="{esc(resource_href(Path(args.extra_css)))}">')
    scripts = []
    if context.mermaid:
        bundle = ROOT / "assets" / "vendor" / "mermaid.min.js"
        if not bundle.exists():
            raise ValueError('Mermaid bundle missing. Run scripts/setup.py (without --skip-mermaid).')
        scripts.append(f'<script src="{esc(copy_resource("mermaid.min.js", bundle))}"></script>')
    scripts.append(f'<script src="{esc(copy_resource("reader-tools.js", ROOT / "assets" / "reader-tools.js"))}"></script>')
    if len(docs) > 1:
        scripts.append(f'<script src="{esc(copy_resource("reading-map.js", ROOT / "assets" / "reading-map.js"))}"></script>')
    scripts.append(f'<script src="{esc(copy_resource("reader.js", ROOT / "assets" / "reader.js"))}"></script>')
    if args.extra_js:
        scripts.append(f'<script src="{esc(resource_href(Path(args.extra_js)))}"></script>')
    for module in args.extra_module:
        scripts.append(f'<script type="module" src="{esc(resource_href(Path(module)))}"></script>')
    graph = graph_data(docs, context.by_path)
    payload = {"id": digest("|".join(str(doc.path) for doc in docs).encode())[:16], "labels": l,
               "documents": [{"id": doc.id, "title": doc.title, "path": doc.relative,
                              "headings": [{key: value for key, value in h.items() if key in {"id", "text", "level"}} for h in doc.headings]} for doc in docs], "graph": graph}
    stats = [(len(docs), l["document_unit"]), (section_count, l["section_unit"]), (images, l["reference_unit"])]
    stats_html = "".join(f'<div class="stat"><strong>{value:02d}</strong><span>{esc(label)}</span></div>' for value, label in stats)
    shell = (ROOT / "assets" / "reader.html").read_text(encoding="utf-8")
    replacements = {"LANG": args.lang, "TITLE": esc(title), "ACCENT": args.accent, "STYLESHEETS": "\n".join(stylesheets),
        "BRAND": esc(l["brand"]), "BOOK_ICON": icon("book"), "SEARCH_ICON": icon("search"), "MENU_ICON": icon("menu"), "SUN_ICON": icon("sun"), "MOON_ICON": icon("moon"), "FOCUS_ICON": icon("focus"), "PRINT_ICON": icon("print"), "CLOSE_ICON": icon("close"), "ARROW_ICON": icon("arrow"),
        "NAV": nav, "STATS": stats_html, "ARTICLES": articles,
        "VISUALS": context.enhancements.get("overview", ""), "GALLERY": gallery_html,
        "READING_MAP": ('<section class="reading-map panel" aria-labelledby="map-title"><div class="section-heading"><div><span class="eyebrow">'+esc(l["overview"])+'</span><h2 id="map-title">'+esc(l["reading_map"])+'</h2></div><p>'+esc(l["reading_map_hint"])+'</p></div><div id="document-map"></div></section>') if len(docs) > 1 else "",
        "START_ID": docs[0].id, "PAYLOAD": json_script(payload), "SCRIPTS": "\n".join(scripts),
        "FONT_LICENSES": json_script({path.stem: path.read_text(encoding='utf-8') for path in sorted((ROOT / 'assets' / 'fonts').glob('*LICENSE.txt'))}),
        "READ_TIME": str(max(1, math.ceil(sum(doc.words for doc in docs)/220)))}
    replacements.update({"L_" + key.upper(): esc(value) for key, value in l.items()})
    # Substitute once: user content containing a template delimiter stays literal.
    page = re.sub(r"@@([A-Z_]+)@@", lambda match: replacements[match.group(1)], shell)
    output.write_text(page, encoding="utf-8", newline="\n")
    warnings = sorted(set(context.warnings + assets.warnings))
    remote = [record["source"] for record in assets.records.values() if record.get("remote")]
    report = {"version": 1, "format": "directory", "output": str(output), "documents": len(docs), "sections": section_count,
              "images": images, "html_bytes": output.stat().st_size, "html_sha256": digest(output.read_bytes()),
              "mermaid": context.mermaid, "theme": str(theme), "theme_sha256": digest(theme.read_bytes()), "offline": not remote, "remote_images": remote, "warnings": warnings,
              "sources": [{"path": doc.relative, "sha256": doc.sha256, "words": doc.words, "tasks": doc.tasks} for doc in docs],
              "assets": list(assets.records.values()), "enhancements_sha256": digest(Path(args.enhancements).read_bytes()) if args.enhancements else None}
    manifest = output.with_suffix(".manifest.json")
    manifest.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return {key: report[key] for key in ("output", "documents", "sections", "images", "html_bytes", "html_sha256", "offline", "warnings")} | {"manifest": str(manifest)}


def build(args, root, docs):
    if args.format == "directory":
        return build_directory(args, root, docs)
    from bundle_html import bundle
    final = Path(args.output).expanduser().resolve()
    with tempfile.TemporaryDirectory(prefix="plan-html-stage-") as temporary:
        staged = copy.copy(args)
        staged.output = str(Path(temporary) / final.name)
        staged.format = "directory"
        summary = build_directory(staged, root, docs)
        packed = bundle(staged.output, final)
        report = json.loads(Path(summary["manifest"]).read_text(encoding="utf-8"))
        report.update({"output": str(final), "format": "single", "html_bytes": packed["html_bytes"],
                       "html_sha256": packed["output_sha256"], "bundle_manifest": packed["manifest"]})
        manifest = final.with_suffix(".manifest.json")
        manifest.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        return {key: report[key] for key in ("output", "documents", "sections", "images", "html_bytes", "html_sha256", "offline", "warnings")} | {"manifest": str(manifest), "bundle_manifest": packed["manifest"]}


def main():
    cli = argparse.ArgumentParser(description=__doc__)
    sub = cli.add_subparsers(dest="command", required=True)
    for command in ("scan", "build"):
        child = sub.add_parser(command)
        child.add_argument("inputs", nargs="+", help="Plan directory, PLAN.md, or Markdown files")
        child.add_argument("--output", "-o", required=command == "build")
        child.add_argument("--explicit", action="store_true", help="Use only the named files, preserving their order")
        child.add_argument("--assets", action="append", default=[], help="Additional reference image folder or file (repeatable)")
        if command == "build":
            child.add_argument("--enhancements", help="Small visual-only JSON specification")
            child.add_argument("--lang", choices=["pt", "en"], default="pt")
            child.add_argument("--accent", choices=["mint", "blue", "amber", "rose"], default="mint")
            child.add_argument("--theme", default="default", help="Theme name from themes/ or path to a compatible CSS theme")
            child.add_argument("--format", choices=["directory", "single"], default="directory", help="Editable separate resources (default), or run the final standalone packager")
            child.add_argument("--asset-mode", choices=["embed", "copy"], help="Image handling during the editable build (default: copy)")
            child.add_argument("--extra-css")
            child.add_argument("--extra-js")
            child.add_argument("--extra-module", action="append", default=[], help="Additional ES module entry (repeatable)")
    args = cli.parse_args()
    try:
        root, docs = discover(args.inputs, args.explicit)
        if args.command == "scan":
            outline = scan(root, docs, args.assets)
            if args.output:
                target = Path(args.output).resolve()
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_text(json.dumps(outline, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
                result = {"outline": str(target), "documents": len(docs), "sections": sum(len(d.headings) for d in docs)}
            else:
                result = outline
        else:
            result = build(args, root, docs)
        print(json.dumps(result, ensure_ascii=False, indent=2))
    except (ValueError, OSError, KeyError, TypeError, RecursionError) as error:
        print(f"plan-html: {error}", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
