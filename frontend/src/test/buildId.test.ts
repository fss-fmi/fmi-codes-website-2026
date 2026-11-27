// @vitest-environment node
import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';
import { build, type HtmlTagDescriptor, type IndexHtmlTransformContext, type Rollup } from 'vite';
import { buildId } from '../../buildId';

const META = /<meta name="build-id" content="([0-9a-f]{12})">/g;

function fixture(script: string) {
  const root = fs.mkdtempSync(path.join(os.tmpdir(), 'build-id-'));
  fs.writeFileSync(
    path.join(root, 'index.html'),
    '<!doctype html><html><head><title>t</title></head><body><script type="module" src="/main.js"></script></body></html>',
  );
  fs.writeFileSync(path.join(root, 'main.js'), script);
  return root;
}

async function builtIds(root: string) {
  const result = await build({
    root,
    configFile: false,
    logLevel: 'silent',
    plugins: [buildId()],
    build: { write: false },
  });
  const output = (Array.isArray(result) ? result[0] : result) as Rollup.RollupOutput;
  const page = output.output.find((file) => file.fileName === 'index.html');
  if (!page || page.type !== 'asset') throw new Error('the build has no index.html');
  return [...String(page.source).matchAll(META)].map((match) => match[1]);
}

type Handler = (html: string, ctx: IndexHtmlTransformContext) => HtmlTagDescriptor[];

function runHook(bundle: Record<string, unknown> | undefined) {
  const { handler } = buildId().transformIndexHtml as unknown as { handler: Handler };
  const ctx = { path: '/index.html', filename: 'index.html', bundle } as IndexHtmlTransformContext;
  return handler('', ctx)[0].attrs?.content;
}

const roots: string[] = [];

afterAll(() => {
  for (const root of roots) fs.rmSync(root, { recursive: true, force: true });
});

test('a real build writes one build id, the same for the same source and new for an edit', async () => {
  const first = fixture('console.log("one");');
  const again = fixture('console.log("one");');
  const edited = fixture('console.log("two");');
  roots.push(first, again, edited);

  const ids = await builtIds(first);
  expect(ids).toHaveLength(1);
  expect(await builtIds(again)).toEqual(ids);
  const editedIds = await builtIds(edited);
  expect(editedIds).toHaveLength(1);
  expect(editedIds[0]).not.toBe(ids[0]);
});

test('a renamed bundle file gives a new id', () => {
  const before = runHook({ 'assets/index-aaa.js': {}, 'assets/index-bbb.css': {} });
  const after = runHook({ 'assets/index-aaa.js': {}, 'assets/index-ccc.css': {} });
  expect(after).not.toBe(before);
});

test('the order of the bundle keys does not change the id', () => {
  const sorted = runHook({ 'assets/a.js': {}, 'assets/b.css': {}, 'assets/c.js': {} });
  const shuffled = runHook({ 'assets/c.js': {}, 'assets/a.js': {}, 'assets/b.css': {} });
  expect(sorted).toMatch(/^[0-9a-f]{12}$/);
  expect(shuffled).toBe(sorted);
});

test('html files in the bundle do not count', () => {
  const assets = { 'assets/a.js': {}, 'assets/b.css': {} };
  expect(runHook({ ...assets, 'index.html': {}, 'other.html': {} })).toBe(runHook(assets));
});

test('a missing bundle fails the build instead of writing no id', () => {
  expect(() => runHook(undefined)).toThrow(/no bundle/);
});
