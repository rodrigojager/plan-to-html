// Development-only research client. No dependency on this MCP enters generated HTML.
import {Client} from '../../.vendor/design-inspiration-mcp/node_modules/@modelcontextprotocol/sdk/dist/esm/client/index.js';
import {StdioClientTransport} from '../../.vendor/design-inspiration-mcp/node_modules/@modelcontextprotocol/sdk/dist/esm/client/stdio.js';
import {fileURLToPath} from 'node:url';
import {mkdir, writeFile} from 'node:fs/promises';
import {execFileSync} from 'node:child_process';

const repo = fileURLToPath(new URL('../../.vendor/design-inspiration-mcp/', import.meta.url));
const expressive = process.argv.includes('--expressive');
const output = fileURLToPath(new URL(expressive ? './research-expressive/' : './research/', import.meta.url));
await mkdir(output, {recursive: true});
const transport = new StdioClientTransport({command: 'node', args: [repo + 'src/index.js'], cwd: repo, stderr: 'pipe'});
const client = new Client({name: 'plan-html-theme-research', version: '1.0.0'});
try {
  await client.connect(transport);
  const inventory = await client.listTools();
  const requests = expressive ? [
    ['neon', 'get_color_palettes', {mood: 'neon cyberpunk', count: 3}],
    ['earth', 'get_color_palettes', {mood: 'earthy organic', count: 3}],
    ['vintage-type', 'get_typography_pairings', {style: 'vintage', count: 3}],
    ['playful-type', 'get_typography_pairings', {style: 'playful', count: 3}],
    ['brutalism', 'get_design_skills', {category: 'brutalism', difficulty: 'all'}],
    ['texture', 'get_design_skills', {category: 'texture', difficulty: 'all'}],
    ['interaction', 'get_animation_library', {category: 'interaction', trigger: 'any', difficulty: 'all'}],
    ['motion', 'get_accessibility_guide', {component: 'motion', level: 'AA'}],
  ] : [
    ['brands', 'browse_brand_designs', {}],
    ...['claude', 'linear.app', 'ibm', 'mintlify', 'stripe', 'notion', 'airbnb', 'framer', 'superhuman', 'apple'].map(brand => [brand, 'browse_brand_designs', {brand}]),
    ['editorial-type', 'get_typography_pairings', {style: 'editorial', count: 3}],
    ['academic-type', 'get_typography_pairings', {style: 'academic', count: 2}],
    ['tech-type', 'get_typography_pairings', {style: 'modern tech', count: 3}],
    ['earth-palettes', 'get_color_palettes', {mood: 'earthy organic', count: 3}],
    ['mono-palettes', 'get_color_palettes', {mood: 'monochrome', count: 3}],
    ['corporate-palettes', 'get_color_palettes', {mood: 'corporate trust', count: 3}],
    ['pastel-palettes', 'get_color_palettes', {mood: 'soft pastel', count: 3}],
    ['contrast-guide', 'get_accessibility_guide', {component: 'contrast', level: 'AA'}],
    ['type-tokens', 'generate_design_tokens', {brand_color: '#315da5', mode: 'light', rounding: 'minimal', transitions: 'snappy'}],
  ];
  const report = {repository: 'https://github.com/notsointresting/design-inspiration-mcp', commit: execFileSync('git', ['rev-parse', 'HEAD'], {cwd: repo, encoding: 'utf8'}).trim(), tool_count: inventory.tools.length, calls: []};
  for (const [id, name, args] of requests) {
    const result = await client.callTool({name, arguments: args});
    await writeFile(output + id + '.json', JSON.stringify(result, null, 2) + '\n');
    const text = result.content?.filter(item => item.type === 'text').map(item => item.text).join('\n') || '';
    report.calls.push({id, tool: name, arguments: args, isError: !!result.isError, characters: text.length});
  }
  await writeFile(output + 'manifest.json', JSON.stringify(report, null, 2) + '\n');
  console.log(JSON.stringify(report, null, 2));
} finally {
  await client.close();
}
