# Theme comparison example

[preview.html](../../preview.html) is the existing reading-plan example with a **demo-only** selector. It is self-contained, can be moved to an empty directory and works offline. The light/dark switch remains independent of the selected appearance. The selector has previous/next buttons, remembers its selection and can be collapsed while reading.

This selector is implemented only by `build_preview.py`, `preview.css`, and `preview.js` in this example folder. The normal renderer/template does not import these files or create the selector. Each reusable theme is an ordinary CSS in `themes/`, selected before generation using `--theme NAME`.

| Theme | Appearance | Reference description queried through MCP |
| --- | --- | --- |
| Papel | Warm paper, serif headings, discreet texture | Claude |
| Grafite | Neutral gray, compact headings, thin contours | Linear |
| Carbono | IBM Plex Sans, rectangular controls, technical blue | IBM |
| Jade | Geometric headings, restrained green, soft surfaces | Mintlify |
| Prisma | Navy/violet, geometric headings, layered panels | Stripe |
| Caderno | Serif reading, neutral paper, ochre links | Notion and editorial typography |
| Coral | Rounded cards/headings, rose accent | Airbnb |
| Studio | Strong headings, high contrast, blue accent | Framer |
| Íris | Muted violet, warm neutrals, layered panels | Superhuman |
| Polar | White/silver, restrained blue, rounded panels | Apple |

All ten previous profiles and their CSS files are preserved. Ten more are appended in a separate selector group:

| New theme | Appearance | Motion |
| --- | --- | --- |
| Neon / Laser | Luminous contours, grid, cyan/magenta, narrow laser selection edge | Laser and glowing hover |
| Manuscrito | Handwritten headings/prose, ruled sheets, sketched edges | Static |
| Crayon | Colored strokes, paper grain, rough frames | Brief sketch hover and marker reveal |
| Papiro | Fibers, aged sheet edges, old manuscript typography | Static |
| Jornal | Serif masthead, drop caps, double rules, monochrome ink | Static |
| Moderno | Frosted toolbar, ambient light, soft depth | Floating hover |
| Minimalista | Flat surfaces, light headings, thin selection rule | Static |
| Maximalista | Poster typography, bold outlines, hard offset shadows | Displacement and selection stripes |
| Art Déco | Geometric frames, gold, spaced serif headings | Static |
| Terminal | Monospaced interface, square edges, green selection | Static |

These are adaptations for long document reading, not reproductions of the brands' sites. The reference source is [design-inspiration-mcp](https://github.com/notsointresting/design-inspiration-mcp), commit `817716d983513147cc06611c3e4d6073f912e93f`. `research-mcp.mjs` connected to the real MCP server using its SDK and called `browse_brand_designs`, `get_typography_pairings`, `get_color_palettes`, `get_accessibility_guide`, and `generate_design_tokens`. Raw responses and a call manifest are saved in `research/`; the SDK/MCP dependencies remain under ignored `.vendor/` and are not dependencies of the skill's output.

The additional research in `research-expressive/` queried neon/organic palettes, vintage/playful typography, brutalism, texture, interaction animation and motion accessibility through the same MCP. Only applicable material and interaction ideas were used; generated promotional copy and unrelated page layouts were excluded.

## Deterministic implementation

- `catalog.json` contains the explicit palettes, type choices and finishes.
- `write_themes.py` writes all 20 CSS files from that data without network or AI. `add_expressive_themes.py` appends/updates only the ten new profiles and deterministically creates their seeded SVG textures/masks in `themes/resources/`.
- The reader uses generic variables in `assets/styles/appearance.css` and `skins.css`; Markdown parsing, semantic content, navigation and interaction logic are shared by every theme. Themes choose existing material/state hooks and keyframes, with no theme-specific JavaScript or DOM branches.
- Type, rounding, shadows and optional CSS textures/gradients vary without introducing theme-specific markup, content interpretation, React, server APIs or remote fonts.
- Fonts are local pinned Fontsource files, installed by `scripts/setup.py`; their licenses are included in the skill and final HTML.
- The example loads the exact same CSS files a normal `--theme NAME` build uses. Its final packager embeds all 20 stylesheets, local SVG materials and their font dependencies. Normal output embeds only its selected CSS and referenced resources.
- The generic `planhtml:styles-changed` / `planhtml:styles-ready` hooks let an extension ask the reader to redraw diagrams after stylesheet/font changes. They do not add a selector or select an appearance in normal output.

Slogans, source-text rewriting, custom cursors, and effects that obstruct selection/navigation were omitted. Fonts, strokes, paper, frames and interaction states provide differentiation while retaining document readability. Every animated profile respects reduced motion; six new profiles are static even without that preference. Libraries delivered by CDN are eligible if downloaded and incorporated locally; an actual live backend/API would still need an offline equivalent.

## Rebuild

```text
python examples/theme-preview/write_themes.py
python examples/theme-preview/build_preview.py
python examples/theme-preview/check_preview.py
```

The first command is needed only when changing catalog data. The second rebuilds the existing example with the preview controls. The third builds every theme through the normal CLI and tests the relocated standalone files, the 40 preview states, navigation, search, diagrams, reading preferences, mobile layout, source preservation, contrast pairs, actual hover/selected effects, local font loading, reduced motion and absence of the selector in normal builds. HTTP(S) requests are blocked. `--only-new` limits verification to the new collection; `--skip-static-builds` skips the ordinary output builds. Existing preservation hashes, when present under `.test-output/theme-gallery/`, are also checked.

To regenerate the authored expressive profiles and deterministic SVG materials, run `python examples/theme-preview/add_expressive_themes.py` before the three commands above. It preserves the previous profiles and does not duplicate new entries.

For a normal deliverable without the comparison controls:

```text
python scripts/plan_html.py build PLAN.md --theme papel --output plano.html --format single
```

To repeat the optional MCP research, first clone the source into `.vendor/design-inspiration-mcp` and run `npm ci --ignore-scripts` there, then `node examples/theme-preview/research-mcp.mjs` (original queries) or `node examples/theme-preview/research-mcp.mjs --expressive` (additional material/interaction queries). This is not required to use, rebuild or package the themes.
