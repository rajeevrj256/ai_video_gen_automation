// Render several still frames with one bundle (the CLI re-bundles for every `remotion still`).
// Used by reelgen/thumbnail.py: clean frames of a video (captions off) and the thumbnail itself.
//   node scripts/stills.mjs job.json
// job.json: {"composition": "Long", "props": {...}, "publicDir": "...", "stills": [{"frame": 120, "out": "a.jpg"}]}
import {readFileSync} from 'node:fs';
import path from 'node:path';
import {fileURLToPath} from 'node:url';
import {bundle} from '@remotion/bundler';
import {renderStill, selectComposition} from '@remotion/renderer';

const job = JSON.parse(readFileSync(process.argv[2], 'utf8'));
const root = path.dirname(path.dirname(fileURLToPath(import.meta.url)));
const chrome = (process.env.REEL_CHROME || '').trim();
const gl = (process.env.REEL_GL || '').trim();
const browser = chrome ? {browserExecutable: chrome, chromeMode: 'chrome-for-testing'} : {};
const chromiumOptions = gl && !gl.startsWith('#') ? {gl} : {};

const serveUrl = await bundle({entryPoint: path.join(root, 'src', 'index.ts'), publicDir: job.publicDir});
const composition = await selectComposition({serveUrl, id: job.composition, inputProps: job.props, ...browser, chromiumOptions});
for (const s of job.stills) {
  await renderStill({
    serveUrl,
    composition,
    inputProps: job.props,
    frame: Math.min(Math.max(0, s.frame), composition.durationInFrames - 1),
    output: s.out,
    imageFormat: s.out.endsWith('.png') ? 'png' : 'jpeg',
    jpegQuality: 92,
    scale: s.scale ?? 1,
    ...browser,
    chromiumOptions,
  });
  console.log('still', s.out);
}
