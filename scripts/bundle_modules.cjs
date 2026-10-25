/* Optional deterministic module build. Invoked by bundle_html.py, never by the reader. */
const fs = require('node:fs');
const path = require('node:path');
const esbuild = require(path.join(__dirname, '..', '.vendor', 'node', 'node_modules', 'esbuild'));
const input = JSON.parse(fs.readFileSync(0, 'utf8'));
(async () => {
  const options = {
    absWorkingDir: input.root,
    bundle: true, write: false, metafile: true, platform: 'browser', format: 'esm',
    target: 'es2022', charset: 'utf8', legalComments: 'inline', sourcemap: false,
    outfile: 'bundle.js', logLevel: 'silent',
    loader: {'.svg':'dataurl','.png':'dataurl','.jpg':'dataurl','.jpeg':'dataurl','.webp':'dataurl','.gif':'dataurl','.bmp':'dataurl','.woff':'dataurl','.woff2':'dataurl','.ttf':'dataurl'},
    external: ['https://*', 'http://*', 'data:*']
  };
  if (input.path) options.entryPoints = [input.path];
  else options.stdin = {contents:input.code, resolveDir:input.directory, sourcefile:'inline-entry.js', loader:'js'};
  const result = await esbuild.build(options);
  const external = Object.values(result.metafile.outputs).flatMap(value => value.imports).filter(value => value.external && !value.path.startsWith('data:')).map(value => value.path);
  if (external.length) throw new Error('External module imports are not self-contained: ' + external.join(', '));
  // Dynamic URL construction cannot be resolved by an ordinary module bundler.
  const blockers = result.warnings.filter(item => ['unsupported-dynamic-import', 'unsupported-require-call'].includes(item.id));
  if (blockers.length) throw new Error(blockers.map(item=>item.text).join('\n'));
  const output = result.outputFiles.find(file=>file.path.endsWith('.js'));
  const css = result.outputFiles.find(file=>file.path.endsWith('.css'));
  const dependencies = Object.keys(result.metafile.inputs).filter(file=>file !== 'inline-entry.js' && !file.startsWith('<')).map(file=>path.resolve(input.root,file));
  process.stdout.write(JSON.stringify({code:output.text,css:css?.text || '',dependencies,warnings:result.warnings.map(item=>item.text)}));
})().catch(error => { process.stderr.write(error.message+'\n'); process.exitCode=1; });
