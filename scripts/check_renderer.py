#!/usr/bin/env python3
"""Behavioral regression checks for the renderer; only uses an isolated temporary plan."""
import hashlib
from html.parser import HTMLParser
import json
from pathlib import Path
import re
import shutil
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]


class Elements(HTMLParser):
    def __init__(self, page):
        super().__init__()
        self.ids, self.links, self.images = [], [], []
        self.feed(page)

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        if "id" in attrs:
            self.ids.append(attrs["id"])
        if tag == "a" and "href" in attrs:
            self.links.append(attrs["href"])
        if tag == "img":
            self.images.append(attrs.get("src", ""))


class RendererChecks(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="plan-html-check-")
        self.folder = Path(self.temp.name)
        self.plan = self.folder / "plan"
        shutil.copytree(ROOT / "examples" / "reading-plan", self.plan)
        self.output = self.folder / "reader.html"

    def tearDown(self):
        self.temp.cleanup()

    def run_cli(self, command="build", *options, succeeds=True):
        args = [sys.executable, str(ROOT / "scripts" / "plan_html.py"), command, str(self.plan)]
        if command == "build":
            args += ["--output", str(self.output)]
            if "--format" not in options:
                args += ["--format", "single"]
        result = subprocess.run(args + list(options), capture_output=True, text=True, encoding="utf-8")
        if succeeds:
            self.assertEqual(result.returncode, 0, result.stderr)
            return json.loads(result.stdout)
        self.assertNotEqual(result.returncode, 0)
        return result.stderr

    def test_repeatable_complete_build_and_unchanged_sources(self):
        before = {str(p): hashlib.sha256(p.read_bytes()).hexdigest() for p in self.plan.rglob("*.md")}
        report = self.run_cli("build", "--enhancements", str(self.plan / "enhancements.json"))
        first = self.output.read_bytes()
        self.run_cli("build", "--enhancements", str(self.plan / "enhancements.json"))
        self.assertEqual(hashlib.sha256(first).hexdigest(), hashlib.sha256(self.output.read_bytes()).hexdigest())
        after = {str(p): hashlib.sha256(p.read_bytes()).hexdigest() for p in self.plan.rglob("*.md")}
        self.assertEqual(before, after)
        self.assertEqual(report["documents"], 4)
        self.assertEqual(report["images"], 2)
        self.assertEqual(report["warnings"], [])
        outline = self.run_cli("scan")
        self.assertEqual([d["path"] for d in outline["documents"]],
                         ["PLAN.md", "01-experiencia.md", "02-conversao.md", "03-decisoes.md"])
        page = first.decode("utf-8")
        self.assertTrue("rastreável até o arquivo de origem" in page, "Expected source fragment missing")
        self.assertTrue("Este checklist registra itens do exemplo" in page, "Expected source fragment missing")
        manifest = json.loads(self.output.with_suffix(".manifest.json").read_text(encoding="utf-8"))
        tasks = next(source["tasks"] for source in manifest["sources"] if source["path"] == "02-conversao.md")
        self.assertEqual(tasks, {"total": 3, "checked": 2})

    def test_internal_links_footnotes_and_heading_collisions(self):
        (self.plan / "04-repeated.md").write_text('# Repeated\n\n## Rastreabilidade\n\n[First](#rastreabilidade)\n\n## Rastreabilidade\n\n[Second](#rastreabilidade-1)\n\nFootnote[^origem].\n\n[^origem]: Another footnote.\n', encoding="utf-8")
        self.run_cli()
        elements = Elements(self.output.read_text(encoding="utf-8"))
        self.assertEqual(len(elements.ids), len(set(elements.ids)), "Duplicate DOM ids")
        broken = [url for url in elements.links if url.startswith("#") and url != "#" and url[1:] not in elements.ids]
        self.assertEqual(broken, [])

    def test_chart_uses_changed_table_and_rejects_unknown_source(self):
        source = self.plan / "02-conversao.md"
        source.write_text(source.read_text(encoding="utf-8").replace('| Texto | 2 |', '| Texto | 17 |'), encoding="utf-8")
        self.run_cli("build", "--enhancements", str(self.plan / "enhancements.json"))
        self.assertTrue('<strong>17</strong>' in self.output.read_text(encoding="utf-8"), "Updated chart value missing")
        spec = json.loads((self.plan / "enhancements.json").read_text(encoding="utf-8"))
        spec["components"][0]["after"] = "02-conversao.md#removed-section"
        (self.plan / "enhancements.json").write_text(json.dumps(spec), encoding="utf-8")
        error = self.run_cli("build", "--enhancements", str(self.plan / "enhancements.json"), succeeds=False)
        self.assertIn("Unknown source heading", error)

    def test_raw_images_safe_html_missing_assets_and_nested_code(self):
        extra = self.plan / "05-assets.md"
        extra.write_text('''# Assets

<img src="references/reader-layout.svg" alt="HTML reference" onload="window.unwanted=true">

![Unavailable](missing-image.png)

<script>window.unwanted=true</script>

```html
<script>this_is_literal()</script>
```

## A title with `inline code`

Literal @@TITLE@@ and <kbd>Ctrl</kbd>.
''', encoding="utf-8")
        report = self.run_cli()
        page = self.output.read_text(encoding="utf-8")
        elements = Elements(page)
        self.assertTrue(all(src.startswith("data:image/") for src in elements.images if src))
        self.assertTrue('onload="window.unwanted=true"' not in page, "Unexpected fragment in page")
        self.assertTrue('<script>window.unwanted=true</script>' not in page, "Unexpected fragment in page")
        self.assertTrue('&lt;script&gt;this_is_literal()&lt;/script&gt;' in re.sub(r'<[^>]+>', '', page), 'Literal code text changed')
        self.assertTrue('Literal @@TITLE@@' in page, "Expected source fragment missing")
        self.assertTrue(any('Missing image' in warning for warning in report["warnings"]))

    def test_copied_assets_and_bounded_discovery(self):
        outside = self.folder / "unrelated.md"
        outside.write_text("# Unrelated repository material", encoding="utf-8")
        self.run_cli("build", "--asset-mode", "copy", "--format", "directory")
        elements = Elements(self.output.read_text(encoding="utf-8"))
        for image in elements.images:
            if image:
                self.assertTrue((self.output.parent / image).is_file(), image)
        outline = self.run_cli("scan")
        self.assertNotIn("unrelated.md", [doc["path"] for doc in outline["documents"]])
        self.assertEqual(len(outline["documents"]), 4)

    def test_mermaid_bundle_not_included_without_diagrams(self):
        source = self.plan / "02-conversao.md"
        source.write_text(source.read_text(encoding="utf-8").replace("```mermaid", "```text"), encoding="utf-8")
        self.run_cli()
        manifest = json.loads(self.output.with_suffix('.manifest.json').read_text(encoding='utf-8'))
        self.assertFalse(manifest['mermaid'])
        self.assertLess(self.output.stat().st_size, 600_000)

    def test_source_title_and_body_without_added_opening_copy(self):
        source = self.plan / "PLAN.md"
        source.write_text('# Plano de migração\n\n## Problema\n\nUma explicação concreta presente somente nesta seção.\n', encoding="utf-8")
        self.run_cli()
        page = self.output.read_text(encoding="utf-8")
        self.assertTrue('<h1>Plano de migração</h1>' in page, "Expected source fragment missing")
        self.assertTrue('<p class="hero-subtitle">' not in page, "Unexpected fragment in page")
        self.assertEqual(page.count('Uma explicação concreta presente somente nesta seção.'), 1)
        # Generic opening-copy fields cannot override the source through a visual spec.
        for field in ("subtitle", "title", "intro"):
            with self.subTest(field=field):
                spec = self.folder / "invalid-enhancements.json"
                spec.write_text(json.dumps({"version": 1, field: "Added opening copy", "components": []}), encoding="utf-8")
                error = self.run_cli("build", "--enhancements", str(spec), succeeds=False)
                self.assertIn('Unsupported document-level fields: ' + field, error)

    def test_visual_title_defaults_to_source_section(self):
        spec = json.loads((self.plan / "enhancements.json").read_text(encoding="utf-8"))
        visual = spec["components"][0]
        del visual["title"]
        spec["components"] = [visual]
        target = self.folder / "source-title-enhancements.json"
        target.write_text(json.dumps(spec), encoding="utf-8")
        self.run_cli("build", "--enhancements", str(target))
        self.assertTrue('<h3>Tipos de entrada</h3>' in self.output.read_text(encoding="utf-8"), "Source title missing")


if __name__ == "__main__":
    unittest.main(verbosity=2)
