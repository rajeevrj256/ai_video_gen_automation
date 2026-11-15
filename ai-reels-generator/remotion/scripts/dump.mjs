// The Blender bridge's first pass (reelgen/lowpoly/blend.py): every frame of a low-poly film rendered with no image
// (imageFormat 'none'), so each frame only runs the editor, whose Dump component sends that frame's 3D scene to the
// receiver in the job.
//   node scripts/dump.mjs job.json
// job.json: {"composition": "LowPoly", "props": {... "dump": {"url": "http://127.0.0.1:port"}}, "publicDir": "...",
//            "frames": [first, last], "concurrency": 4, "timeout": 180000}
import {readFileSync} from 'node:fs';
import path from 'node:path';
import {fileURLToPath} from 'node:url';
import {bundle} from '@remotion/bundler';
import {openBrowser, renderFrames, selectComposition} from '@remotion/renderer';

const job = JSON.parse(readFileSync(process.argv[2], 'utf8'));
const root = path.dirname(path.dirname(fileURLToPath(import.meta.url)));
const chrome = (process.env.REEL_CHROME || '').trim();
const gl = (process.env.REEL_GL || '').trim();
const browserOpts = chrome.toLowerCase() === 'chrome-for-testing' ? {chromeMode: 'chrome-for-testing'}
  : chrome ? {browserExecutable: chrome, chromeMode: 'chrome-for-testing'} : {};
const chromiumOptions = gl && !gl.startsWith('#') ? {gl} : {};

const serveUrl = await bundle({entryPoint: path.join(root, 'src', 'index.ts'), publicDir: job.publicDir});
const composition = await selectComposition({serveUrl, id: job.composition, inputProps: job.props, ...browserOpts, chromiumOptions});
const [first, last] = job.frames ?? [0, composition.durationInFrames - 1];
const total = last - first + 1;
let done = 0;
let shown = 0;
await renderFrames({
  serveUrl,
  composition,
  inputProps: job.props,
  imageFormat: 'none',
  frameRange: [first, Math.min(last, composition.durationInFrames - 1)],
  concurrency: job.concurrency ?? null,
  timeoutInMilliseconds: job.timeout ?? 180000,
  ...browserOpts,
  chromiumOptions,
  onStart: () => {},
  onFrameUpdate: (n) => {
    done = n;
    if (done - shown >= Math.max(1, Math.round(total / 50)) || done === total) {
      shown = done;
      console.log(`@@DUMP@@ ${JSON.stringify({done, total})}`);
    }
  },
  outputDir: null,
});
console.log(`@@DUMP@@ ${JSON.stringify({done: total, total, finished: true})}`);
process.exit(0);
