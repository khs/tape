import { renderers } from './renderers.mjs';
import { c as createExports, s as serverEntrypointModule } from './chunks/_@astrojs-ssr-adapter_BXWVnLfY.mjs';
import { manifest } from './manifest_C6f_uKLY.mjs';

const serverIslandMap = new Map();;

const _page0 = () => import('./pages/_image.astro.mjs');
const _page1 = () => import('./pages/compose.astro.mjs');
const _page2 = () => import('./pages/custom.astro.mjs');
const _page3 = () => import('./pages/library.json.astro.mjs');
const _page4 = () => import('./pages/me.astro.mjs');
const _page5 = () => import('./pages/u/_slug_.astro.mjs');
const _page6 = () => import('./pages/index.astro.mjs');
const _page7 = () => import('./pages/_---slug_.astro.mjs');
const pageMap = new Map([
    ["node_modules/astro/dist/assets/endpoint/generic.js", _page0],
    ["src/pages/compose.astro", _page1],
    ["src/pages/custom.astro", _page2],
    ["src/pages/library.json.ts", _page3],
    ["src/pages/me/index.astro", _page4],
    ["src/pages/u/[slug].astro", _page5],
    ["src/pages/index.astro", _page6],
    ["src/pages/[...slug].astro", _page7]
]);

const _manifest = Object.assign(manifest, {
    pageMap,
    serverIslandMap,
    renderers,
    actions: () => import('./noop-entrypoint.mjs'),
    middleware: () => import('./_noop-middleware.mjs')
});
const _args = {
    "middlewareSecret": "d58925f5-ace4-4b5f-a958-b5714da6a8da",
    "skewProtection": false
};
const _exports = createExports(_manifest, _args);
const __astrojsSsrVirtualEntry = _exports.default;
const _start = 'start';
if (Object.prototype.hasOwnProperty.call(serverEntrypointModule, _start)) ;

export { __astrojsSsrVirtualEntry as default, pageMap };
