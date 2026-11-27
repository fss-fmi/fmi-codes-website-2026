import { createHash } from 'node:crypto';
import type { IndexHtmlTransformContext, Plugin } from 'vite';

/**
 * Writes `<meta name="build-id" content="<hash>" data-built-at="<epoch ms>">` into the built
 * index.html. The hash covers the bundle's file names, which carry Vite's content hashes, so it
 * changes only when the built JS or CSS does; the build time lets an open tab tell a newer
 * build from an old pod still serving mid-rollout (nextState in src/lib/buildId.ts).
 */
export function buildId(): Plugin {
  return {
    name: 'build-id',
    apply: 'build',
    transformIndexHtml: {
      order: 'post',
      handler(_html: string, ctx: IndexHtmlTransformContext) {
        // A silent skip would switch the new-version banner off for good with nothing failing.
        if (!ctx.bundle) throw new Error('build-id: Vite passed no bundle to transformIndexHtml');
        // .html keys left out: a second page would otherwise see the first one's name. Plain
        // sort, not localeCompare, so Windows and Linux builds agree.
        const names = Object.keys(ctx.bundle)
          .filter((name) => !name.endsWith('.html'))
          .sort();
        const id = createHash('sha256').update(names.join('\n')).digest('hex').slice(0, 12);
        return [
          {
            tag: 'meta',
            attrs: { name: 'build-id', content: id, 'data-built-at': String(Date.now()) },
            injectTo: 'head',
          },
        ];
      },
    },
  };
}
