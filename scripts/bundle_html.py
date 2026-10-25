#!/usr/bin/env python3
"""Package an existing HTML document and its local static resources into one file."""
from __future__ import annotations

import argparse
import base64
import hashlib
import html
from html.parser import HTMLParser
import json
import mimetypes
from pathlib import Path
import re
import shutil
import subprocess
import sys
from urllib.parse import unquote, urlsplit
from urllib.request import url2pathname

ROOT = Path(__file__).resolve().parents[1]
MIME = {'.svg':'image/svg+xml','.png':'image/png','.bmp':'image/bmp',
        '.woff':'font/woff','.woff2':'font/woff2','.ttf':'font/ttf','.otf':'font/otf','.mjs':'text/javascript'}
sys.path.insert(0, str(ROOT / ".vendor"))
try:
    import tinycss2
except ImportError:
    raise SystemExit(f'Dependencies missing. Run: python "{ROOT / "scripts" / "setup.py"}" --skip-mermaid')


def sha(data):
    return hashlib.sha256(data).hexdigest()


def data_url(data, mime):
    return "data:" + mime + ";base64," + base64.b64encode(data).decode("ascii")


def css_string(value):
    return '"' + tinycss2.serializer.serialize_string_value(value) + '"'


def srcset_candidates(value):
    """Split according to srcset URL/descriptor boundaries, including data URLs."""
    position = 0
    while position < len(value):
        while position < len(value) and (value[position].isspace() or value[position] == ','):
            position += 1
        start = position
        while position < len(value) and not value[position].isspace():
            position += 1
        url = value[start:position]
        if not url:
            return
        if url.endswith(','):
            yield url.rstrip(','), ''
            continue
        start, depth = position, 0
        while position < len(value):
            char = value[position]
            if char == '(':
                depth += 1
            elif char == ')':
                depth -= 1
            elif char == ',' and depth == 0:
                break
            position += 1
        yield url, value[start:position].strip()
        position += 1


class Packer:
    def __init__(self, source, root=None, allow_external=False):
        self.source = Path(source).resolve()
        self.root = Path(root).resolve() if root else self.source.parent
        self.allow_external = allow_external
        self.dependencies = {}
        self.external = set()
        self.cache = {}
        self.active = set()
        self.module_dependencies = []
        self.module_css = []

    def local(self, url, origin):
        parsed = urlsplit(url)
        if not url or url.startswith('#') or parsed.scheme == 'data':
            return None
        if parsed.scheme == 'file':
            return Path(url2pathname(parsed.path)).resolve()
        if parsed.scheme or parsed.netloc:
            self.external.add(url)
            if not self.allow_external:
                raise ValueError(f'External resource: {url}. Save it locally first, or use --allow-external for a non-standalone output.')
            return None
        path = unquote(parsed.path)
        if path.startswith('/'):
            target = self.root / path.lstrip('/')
        else:
            target = origin.parent / path
        target = target.resolve()
        if not target.is_file():
            raise ValueError(f'Missing resource: {url} (from {origin})')
        return target

    def read(self, path):
        data = path.read_bytes()
        self.dependencies.setdefault(str(path), {'path': str(path), 'bytes': len(data), 'sha256': sha(data)})
        return data

    def resource(self, url, origin, kind=None):
        path = self.local(url, origin)
        if path is None:
            return url
        key = (path, kind)
        if key in self.active:
            raise ValueError(f'Circular resource import: {path}')
        if key not in self.cache:
            self.active.add(key)
            try:
                payload = self.read(path)
                mime = MIME.get(path.suffix.lower()) or mimetypes.guess_type(path.name)[0] or 'application/octet-stream'
                if kind == 'css':
                    rules, _ = tinycss2.parse_stylesheet_bytes(payload)
                    payload = self.css_rules(rules, path).encode('utf-8')
                    mime = 'text/css;charset=utf-8'
                elif kind == 'script':
                    mime = 'text/javascript;charset=utf-8'
                elif kind == 'module':
                    payload = self.module(path=path).encode('utf-8')
                    mime = 'text/javascript;charset=utf-8'
                elif path.suffix.lower() == '.svg':
                    payload = HTMLBundle(payload.decode('utf-8-sig'),self,origin=path).result().encode('utf-8')
                    mime = 'image/svg+xml'
                self.cache[key] = data_url(payload, mime)
            finally:
                self.active.remove(key)
        fragment = urlsplit(url).fragment
        return self.cache[key] + ('#' + fragment if fragment else '')

    def module(self, path=None, code=None, origin=None):
        node = shutil.which('node')
        library = ROOT / '.vendor' / 'node' / 'node_modules' / 'esbuild'
        if not node or not library.exists():
            raise ValueError('ES modules require Node.js and isolated esbuild. Run scripts/setup.py --skip-mermaid --with-js-bundler.')
        request = {'root':str(self.root), 'path':str(path) if path else None,
                   'code':code, 'directory':str((origin or path or self.source).parent)}
        result = subprocess.run([node,str(ROOT/'scripts'/'bundle_modules.cjs')], input=json.dumps(request),
                                text=True,encoding='utf-8',capture_output=True,timeout=90)
        if result.returncode:
            raise ValueError('Module bundle failed: ' + result.stderr.strip())
        bundle = json.loads(result.stdout)
        paths = {Path(value).resolve() for value in bundle['dependencies'] if Path(value).is_file()}
        shared = set().union(*self.module_dependencies) & paths if self.module_dependencies else set()
        if shared:
            raise ValueError('Separate module entries share dependencies. Use one entry module that imports the others to preserve shared state.')
        self.module_dependencies.append(paths)
        for dependency in sorted(paths):
            self.read(dependency)
        if bundle['css']:
            self.module_css.append(bundle['css'])
        return bundle['code']

    def css_values(self, tokens, origin):
        for index, token in enumerate(tokens):
            if token.type == 'url':
                url = self.resource(token.value, origin)
                tokens[index] = tinycss2.parse_component_value_list('url(' + css_string(url) + ')')[0]
            elif token.type == 'function':
                if token.lower_name == 'url':
                    values = [part for part in token.arguments if part.type not in {'whitespace','comment'}]
                    if len(values) == 1 and values[0].type == 'string':
                        url = self.resource(values[0].value, origin)
                        token.arguments = tinycss2.parse_component_value_list(css_string(url))
                elif token.lower_name in {'image-set','-webkit-image-set'}:
                    # image-set permits bare string URLs as well as url(...).
                    for j, item in enumerate(token.arguments):
                        if item.type == 'string':
                            url = self.resource(item.value, origin)
                            token.arguments[j] = tinycss2.parse_component_value_list(css_string(url))[0]
                    self.css_values(token.arguments, origin)
                else:
                    self.css_values(token.arguments, origin)
            elif hasattr(token, 'content') and token.content is not None:
                self.css_values(token.content, origin)
        return tokens

    def css_rules(self, rules, origin):
        result = []
        for rule in rules:
            if rule.type == 'at-rule' and rule.lower_at_keyword == 'charset':
                continue
            if rule.type == 'at-rule' and rule.lower_at_keyword == 'import':
                values = [(i,t) for i,t in enumerate(rule.prelude) if t.type not in {'whitespace','comment'}]
                if values:
                    index, target = values[0]
                    if target.type in {'string','url'}:
                        url = target.value
                    elif target.type == 'function' and target.lower_name == 'url':
                        args = [t for t in target.arguments if t.type not in {'whitespace','comment'}]
                        url = args[0].value if len(args)==1 and args[0].type=='string' else None
                    else:
                        url = None
                    if url is None:
                        raise ValueError(f'Unsupported CSS import in {origin}')
                    embedded = self.resource(url, origin, 'css')
                    rule.prelude[index] = tinycss2.parse_component_value_list(css_string(embedded))[0]
            elif hasattr(rule,'prelude'):
                self.css_values(rule.prelude,origin)
            if hasattr(rule,'content') and rule.content is not None:
                # Nested @imports are invalid CSS; nested rule values still need URLs.
                self.css_values(rule.content,origin)
            result.append(rule)
        return tinycss2.serialize(result)

    def css(self, text, origin, declarations=False):
        if declarations:
            return tinycss2.serialize(self.css_values(tinycss2.parse_component_value_list(text),origin))
        return self.css_rules(tinycss2.parse_stylesheet(text),origin)


ATTR = re.compile(r'''(?P<name>[^\s=<>/]+)(?:\s*=\s*(?:"(?P<double>[^"]*)"|'(?P<single>[^']*)'|(?P<bare>[^\s>]+)))?''')


def rewrite_tag(raw, changes, remove=()):
    """Patch only attributes, preserving SVG casing and unrelated source bytes."""
    begin = re.match(r'<\s*[^\s/>]+',raw).end()
    edits, seen = [], set()
    for match in ATTR.finditer(raw,begin):
        name = match.group('name').lower()
        if name in remove:
            edits.append((match.start(),match.end(),''))
        elif name in changes:
            seen.add(name)
            replacement = f'{match.group("name")}="{html.escape(changes[name],quote=True)}"'
            edits.append((match.start(),match.end(),replacement))
    for start,end,text in reversed(edits):
        raw = raw[:start]+text+raw[end:]
    missing = [(name,value) for name,value in changes.items() if name not in seen]
    if missing:
        index = raw.rfind('/>') if raw.rstrip().endswith('/>') else raw.rfind('>')
        raw = raw[:index] + ''.join(f' {name}="{html.escape(value,quote=True)}"' for name,value in missing) + raw[index:]
    return raw


class HTMLBundle(HTMLParser):
    def __init__(self, text, packer, origin=None):
        super().__init__(convert_charrefs=False)
        self.text, self.packer, self.origin = text, packer, origin or packer.source
        self.offsets = [0]
        for match in re.finditer('\n',text):
            self.offsets.append(match.end())
        self.edits = []
        self.raw_block = None
        self.base_seen = False

    def position(self):
        line,column = self.getpos()
        return self.offsets[line-1]+column

    def handle_startendtag(self,tag,attrs):
        self.handle_starttag(tag,attrs)

    def handle_starttag(self,tag,attrs):
        raw = self.get_starttag_text()
        start,end = self.position(),self.position()+len(raw)
        attrs = dict(attrs)
        changes,remove = {},set()
        if tag == 'base':
            href = attrs.get('href')
            if href and not self.base_seen:
                parsed = urlsplit(href)
                if parsed.scheme or parsed.netloc:
                    raise ValueError('An external <base href> must be resolved to local files before packaging.')
                target = (self.origin.parent/unquote(parsed.path)).resolve()
                self.origin = target/'__index__.html' if href.endswith('/') else target
                self.base_seen = True
            self.edits.append((start,end,''))
            return
        if tag == 'link':
            rel = set((attrs.get('rel') or '').lower().split())
            href = attrs.get('href')
            if 'stylesheet' in rel and href:
                embedded = self.packer.resource(href,self.origin,'css')
                changes['href'] = embedded
                remove.update({'integrity','crossorigin'})
            elif rel & {'icon','apple-touch-icon','mask-icon'} and href:
                changes['href'] = self.packer.resource(href,self.origin)
                remove.update({'integrity','crossorigin'})
            elif rel & {'preconnect','dns-prefetch','preload','modulepreload','prefetch'}:
                self.edits.append((start,end,''))
                return
        if tag == 'script':
            script_type = (attrs.get('type') or '').strip().lower()
            if attrs.get('src'):
                kind = 'module' if script_type=='module' else 'script'
                changes['src'] = self.packer.resource(attrs['src'],self.origin,kind)
                remove.update({'integrity','crossorigin'})
            self.raw_block = {'tag':tag,'start':end,'origin':self.origin,'module':script_type=='module' and not attrs.get('src')}
        elif tag == 'style':
            self.raw_block = {'tag':tag,'start':end,'origin':self.origin}
        if tag in {'img','source','video','audio','track','embed','input'} and attrs.get('src'):
            changes['src'] = self.packer.resource(attrs['src'],self.origin)
        if tag == 'video' and attrs.get('poster'):
            changes['poster'] = self.packer.resource(attrs['poster'],self.origin)
        if tag in {'img','source'} and attrs.get('srcset'):
            changes['srcset'] = ', '.join(self.packer.resource(url,self.origin)+((' '+descriptor) if descriptor else '') for url,descriptor in srcset_candidates(attrs['srcset']))
        if tag in {'image','use'}:
            for name in ('href','xlink:href'):
                if attrs.get(name):
                    changes[name] = self.packer.resource(attrs[name],self.origin)
        if tag == 'a' and 'download' in attrs and attrs.get('href'):
            changes['href'] = self.packer.resource(attrs['href'],self.origin)
        if tag in {'iframe','object'} and (attrs.get('src') or attrs.get('data')):
            raise ValueError('Embedded documents require their own packaging first (iframe/object).')
        if attrs.get('style'):
            changes['style'] = self.packer.css(attrs['style'],self.origin,declarations=True)
        if changes or remove:
            self.edits.append((start,end,rewrite_tag(raw,changes,remove)))

    def handle_endtag(self,tag):
        if not self.raw_block or self.raw_block['tag'] != tag:
            return
        block,self.raw_block = self.raw_block,None
        start,end = block['start'],self.position()
        content = self.text[start:end]
        if tag == 'style':
            replacement = self.packer.css(content,block['origin'])
            replacement = re.sub(r'</style',r'<\\/style',replacement,flags=re.I)
            self.edits.append((start,end,replacement))
        elif block.get('module') and content.strip():
            code = self.packer.module(code=content,origin=block['origin'])
            self.edits.append((start,end,re.sub(r'</script',r'<\\/script',code,flags=re.I)))

    def result(self):
        self.feed(self.text)
        self.close()
        if self.raw_block:
            raise ValueError('Unclosed script/style element')
        chunks, cursor = [], 0
        for start,end,replacement in sorted(self.edits):
            if start < cursor:
                raise ValueError('Overlapping HTML resource edits')
            chunks.extend((self.text[cursor:start],replacement))
            cursor = end
        chunks.append(self.text[cursor:])
        result = ''.join(chunks)
        if self.packer.module_css:
            css = ''.join('<link rel="stylesheet" href="'+data_url(item.encode(),'text/css;charset=utf-8')+'">' for item in self.packer.module_css)
            result = re.sub(r'</head\s*>',lambda match:css+match.group(),result,count=1,flags=re.I)
        return result


def bundle(source, output, root=None, allow_external=False):
    source,output = Path(source).resolve(),Path(output).resolve()
    if source == output:
        raise ValueError('Choose a separate output file; the editable HTML is preserved.')
    packer = Packer(source,root,allow_external)
    original = source.read_bytes()
    page = HTMLBundle(original.decode('utf-8-sig'),packer).result()
    output.parent.mkdir(parents=True,exist_ok=True)
    output.write_text(page,encoding='utf-8',newline='\n')
    report = {'version':1,'input':str(source),'input_sha256':sha(original),'output':str(output),
              'output_sha256':sha(output.read_bytes()),'html_bytes':output.stat().st_size,
              'self_contained_static_resources':not packer.external,'external_resources':sorted(packer.external),
              'runtime_network_checked':False,'embedded_files':len(packer.dependencies),
              'dependencies':[packer.dependencies[key] for key in sorted(packer.dependencies)]}
    manifest = output.with_suffix('.bundle.json')
    manifest.write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    return {key:report[key] for key in ('output','output_sha256','html_bytes','self_contained_static_resources','embedded_files','external_resources')} | {'manifest':str(manifest)}


def main():
    for stream in (sys.stdout,sys.stderr):
        if hasattr(stream,'reconfigure'):
            stream.reconfigure(encoding='utf-8')
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('input',help='Existing HTML with local resource references')
    parser.add_argument('--output','-o',required=True)
    parser.add_argument('--root',help='Document root for /absolute resource URLs (default: input directory)')
    parser.add_argument('--allow-external',action='store_true',help='Keep external URLs and report non-standalone output')
    args = parser.parse_args()
    try:
        print(json.dumps(bundle(args.input,args.output,args.root,args.allow_external),ensure_ascii=False,indent=2))
    except (OSError,ValueError,subprocess.TimeoutExpired) as error:
        print('bundle-html: '+str(error),file=sys.stderr)
        return 2
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
