// Fails when the initial JS is over budget or a lazy chunk has been pulled into the initial graph.
import { readFileSync, existsSync } from 'node:fs';
import { gzipSync } from 'node:zlib';
import { join, dirname } from 'node:path';

const DIST = process.argv[2] ?? 'dist';
const BUDGET_KB = Number(process.env.BUNDLE_BUDGET_KB ?? 450);
const LAZY = [/^DockApp-/]; // chunks that must stay out of the initial graph (the dock shell is lazy)

const html = readFileSync(join(DIST, 'index.html'), 'utf8');
const entries = [...html.matchAll(/(?:src|href)="\/(assets\/[^"]+\.js)"/g)].map((m) => m[1]);
if (entries.length === 0) { console.error('check-bundle: no script entries found in index.html'); process.exit(1); }

const gz = (file) => gzipSync(readFileSync(join(DIST, file))).length;
const staticImports = (file) => {
  const src = readFileSync(join(DIST, file), 'utf8');
  // Static imports look like `from"./x.js"` or `import"./x.js"`; dynamic ones are import("./x.js") and are skipped.
  return [...src.matchAll(/(?:from|^import|;import)\s*["']\.\/([^"']+\.js)["']/g)].map((m) => join(dirname(file), m[1]));
};
const graph = (roots) => {
  const seen = new Set();
  const walk = (f) => { if (seen.has(f) || !existsSync(join(DIST, f))) return; seen.add(f); staticImports(f).forEach(walk); };
  roots.forEach(walk);
  return seen;
};

const initial = graph(entries);
const total = [...initial].reduce((n, f) => n + gz(f), 0);
let failed = false;
console.log(`initial JS: ${(total / 1024).toFixed(1)} kB gzip across ${initial.size} chunk(s) (budget ${BUDGET_KB} kB)`);
if (total / 1024 > BUDGET_KB) { console.error('check-bundle: initial JS is over budget'); failed = true; }
for (const f of initial) {
  if (LAZY.some((re) => re.test(f.split('/').pop()))) { console.error(`check-bundle: lazy chunk ${f} is imported eagerly`); failed = true; }
}
const lazyChunk = [...new Set(readFileSync(join(DIST, entries[0]), 'utf8').match(/assets\/DockApp-[^"']+\.js|\.\/DockApp-[^"']+\.js/g) ?? [])];
if (lazyChunk.length === 0) { console.error('check-bundle: DockApp is no longer a separate lazy chunk'); failed = true; }
else {
  const dock = graph(lazyChunk.map((c) => c.replace(/^\.\//, 'assets/')));
  const dockTotal = [...new Set([...initial, ...dock])].reduce((n, f) => n + gz(f), 0);
  console.log(`dock shell (initial plus lazy graph): ${(dockTotal / 1024).toFixed(1)} kB gzip`);
  if (dockTotal / 1024 > BUDGET_KB) { console.error('check-bundle: dock shell total is over budget'); failed = true; }
}
process.exit(failed ? 1 : 0);
