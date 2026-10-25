# Visual enhancements

Author only the useful additions. Do not repeat the source body. All strings are escaped, and `after`, `sources`, node `ref`, and table references resolve against the plan. Use the exact references from `scan`; a reference is `relative/file.md#heading-slug` (or just the filename for the whole document). `after: "overview"` places a visual before the source documents; any other value inserts it just after the referenced heading. Each visual requires `sources`.

Only `version` and `components` are accepted at the document level. The title always comes from the Markdown; document titles, subtitles, taglines, introductions, and other added opening copy are not configurable. Visual titles and labels identify the actual subject in a few words. Omit generic introductions and promotional language from all text and assets. A component without a `title` uses its first source section's title.

```json
{
  "version": 1,
  "components": [
    {
      "id": "pipeline",
      "type": "mermaid",
      "title": "Conversion flow",
      "after": "overview",
      "sources": ["01-workflow.md#pipeline"],
      "code": "flowchart LR\n A[Input] --> B[Processing]\n B --> C[Output]"
    },
    {
      "id": "comparison",
      "type": "table-chart",
      "title": "Comparison from the plan",
      "after": "02-data.md#comparison",
      "sources": ["02-data.md#comparison"],
      "table": "02-data.md#comparison",
      "table_index": 0,
      "label_column": 0,
      "value_column": 1,
      "unit": "ms",
      "number_format": "en"
    },
    {
      "id": "sequence",
      "type": "timeline",
      "title": "Delivery sequence",
      "after": "overview",
      "sources": ["03-stages.md#delivery"],
      "items": [
        {"label": "Prototype", "detail": "Optional brief explanation", "ref": "03-stages.md#prototype"},
        {"label": "Review", "ref": "03-stages.md#review"}
      ]
    },
    {
      "id": "reference",
      "type": "image",
      "title": "Interface reference",
      "after": "PLAN.md#interface-and-references",
      "sources": ["PLAN.md#interface-and-references"],
      "src": "references/screen.png",
      "alt": "Description of the screen and what it demonstrates"
    }
  ]
}
```

`table-chart` reads values from the actual table, so a data update automatically changes the chart. Column numbers and `table_index` start at zero. Cells must contain one numeric value plus optional units. `number_format: "pt"` accepts `1.234,5`; the default `en` accepts `1,234.5`. Negative values use a shared zero baseline. A chart keeps its source table visible and provides a textual value for every bar.

Mermaid uses strict mode, disables HTML labels, and adapts to both themes. Diagram failures expose the original code and a visible error instead of hiding the content. Do not include Mermaid initialization directives or click handlers. Prefer a few well-labeled nodes over a diagram that merely duplicates the entire document. Give architecture or dependency arrows only when the source actually establishes those relationships.

Image paths are relative to the plan's source root. Extra images may also be passed using `--assets path/to/references`; supported local images are embedded or copied with the other assets. Avoid generated decoration that does not help explain the plan.

Extension hooks (only when built-ins do not cover a real need):

```javascript
document.addEventListener('planhtml:ready', () => { /* scoped interaction */ });
document.addEventListener('planhtml:theme', event => {
  const theme = event.detail.theme; // "light" or "dark"
});
```

The stable DOM surfaces are `.document`, `.prose`, `.enhancement`, `[data-doc-id]`, and `html[data-theme]`. Use CSS variables such as `--bg`, `--surface`, `--text`, `--muted`, `--line`, `--accent`, and `--accent-soft`. Never rely on a light-only color or remove the theme control.
