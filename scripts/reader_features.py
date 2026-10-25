"""Deterministic presentation helpers; no content generation or remote inference."""
import base64
import io
import math
import re
from urllib.parse import unquote_to_bytes
import xml.etree.ElementTree as ET

from PIL import Image, UnidentifiedImageError
from pygments import lex
from pygments.lexers import get_lexer_by_name, TextLexer
from pygments.token import STANDARD_TYPES
from pygments.util import ClassNotFound
import html


def image_dimensions(data):
    try:
        if data.lstrip().startswith(b'<'):
            root = ET.fromstring(data)
            if root.tag.rsplit('}', 1)[-1] != 'svg':
                return {}
            def size(value):
                match = re.fullmatch(r'\s*([\d.]+)(?:px)?\s*', value or '')
                return float(match.group(1)) if match else 0
            width, height = size(root.get('width')), size(root.get('height'))
            view = re.split(r'[\s,]+', (root.get('viewBox') or '').strip())
            if len(view) == 4:
                vw, vh = float(view[2]), float(view[3])
                if vw > 0 and vh > 0:
                    width, height = (width, height or width*vh/vw) if width else (height*vw/vh, height) if height else (vw, vh)
        else:
            with Image.open(io.BytesIO(data)) as image:
                width, height = image.size
                if image.getexif().get(274) in {5, 6, 7, 8}:
                    width, height = height, width
        if all(math.isfinite(v) and v > 0 for v in (width, height)):
            return {'width': max(1, round(width)), 'height': max(1, round(height))}
    except (ValueError, OSError, ET.ParseError, UnidentifiedImageError, Image.DecompressionBombError):
        pass
    return {}


def data_image_bytes(url):
    header, payload = url.split(',', 1)
    return base64.b64decode(payload) if ';base64' in header else unquote_to_bytes(payload)


def highlighted_code(source, language):
    """Use only the declared lexer and preserve source text exactly, including newlines."""
    try:
        lexer = get_lexer_by_name(language, stripnl=False, ensurenl=False, stripall=False)
    except ClassNotFound:
        lexer = TextLexer(stripnl=False, ensurenl=False, stripall=False)
    lines, current = [], []
    for token, text in lex(source, lexer):
        while token not in STANDARD_TYPES and token.parent:
            token = token.parent
        classname = STANDARD_TYPES.get(token, '')
        for piece in re.split('(\n)', text):
            if piece == '\n':
                lines.append((''.join(current), True))
                current = []
            elif piece:
                escaped = html.escape(piece, quote=False)
                current.append(f'<span class="{classname}">{escaped}</span>' if classname else escaped)
    if current:
        lines.append((''.join(current), False))
    return ''.join(f'<span class="code-line" data-line="{index}">{text}</span>' + ('\n' if newline else '')
                   for index, (text, newline) in enumerate(lines, 1))
