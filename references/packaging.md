# Standalone packaging

The editable build and the packaged deliverable are separate artifacts. Complete the design and interactions first, then run:

```text
python SKILL_DIR/scripts/bundle_html.py work/plan.html --output plan.html
```

The packager can also process HTML created outside this skill. It follows the references in the actual file, including:

- Stylesheets, nested CSS `@import`, CSS `url(...)`, `image-set`, fonts, inline `<style>` and `style` attributes.
- Classic JavaScript, retaining script order, `defer`, and `async` behavior.
- ES module entries and their static/literal dynamic imports, using isolated esbuild. Set up once with `python SKILL_DIR/scripts/setup.py --skip-mermaid --with-js-bundler` (requires Node.js/npm). Use one entry module when modules share state.
- Images including SVG, PNG, BMP, JPEG, WebP, responsive `srcset`/`picture`, icons, video posters, and local media references.

Resources become data URLs in the HTML. SVG stays SVG and is encoded with its image MIME type; raster images are Base64 without conversion or quality loss. Scripts also use data URLs, which preserves external-script scheduling semantics that ordinary inline scripts would change. CSS imports retain their media/layer qualifiers. Existing inline markup and source prose are preserved.

The source HTML and its resources remain unchanged. Repeated runs with unchanged inputs produce the same HTML bytes. The `.bundle.json` records dependency paths, byte sizes, hashes, and remaining external references; the stdout report stays compact.

Missing resources stop packaging before writing the deliverable. External resource URLs also stop it by default. To intentionally retain external dependencies, use `--allow-external`; the report then marks static resources as non-standalone. Ordinary hyperlinks remain links and do not count as resource dependencies. Resource paths starting with `/` use the input directory as document root; override with `--root` when needed.

Runtime API calls, WebSockets, service workers, dynamically constructed URLs, and resource paths calculated by JavaScript are not converted into offline services. Keep such features explicit, provide local data when appropriate, and test the final file with network blocked. For complex modules, prebundle from a single entry. CSP rules that prohibit data URLs must be adjusted by the page's author to match the intended standalone artifact. Iframes/embedded documents need their own packaging first.

Browser acceptance should open a copy of the final HTML in an otherwise empty directory with HTTP/HTTPS requests blocked. This proves the page is using incorporated resources rather than accidentally relying on nearby source files. Exercise the actual custom interaction, not just page load.
