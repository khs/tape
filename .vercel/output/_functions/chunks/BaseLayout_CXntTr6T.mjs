import { c as createComponent, d as addAttribute, b as renderTemplate, i as renderHead, j as renderSlot, a as renderScript, e as createAstro } from './astro/server_DWURT7C5.mjs';
import 'piccolore';
import 'clsx';
/* empty css                          */

const $$Astro = createAstro();
const $$BaseLayout = createComponent(async ($$result, $$props, $$slots) => {
  const Astro2 = $$result.createAstro($$Astro, $$props, $$slots);
  Astro2.self = $$BaseLayout;
  const { title, description } = Astro2.props;
  const baseUrl = "/".replace(/\/$/, "");
  return renderTemplate`<html lang="en"> <head><meta charset="UTF-8"><meta name="viewport" content="width=device-width, initial-scale=1.0"><meta name="generator"${addAttribute(Astro2.generator, "content")}><title>${title}</title>${description && renderTemplate`<meta name="description"${addAttribute(description, "content")}>`}${renderHead()}</head> <body class="min-h-screen flex flex-col"> <header class="border-b hairline"> <div class="max-w-[1280px] mx-auto px-6 h-14 flex items-center justify-between"> <a${addAttribute(baseUrl, "href")} class="no-underline text-neutral-900 font-medium">
Legible Markets
</a> <nav class="flex items-center gap-5 text-sm"> <a${addAttribute(`${baseUrl}/compose/`, "href")} class="text-neutral-600 no-underline hover:text-neutral-900">
Compose
</a> <a${addAttribute(`${baseUrl}/me/`, "href")} class="text-neutral-600 no-underline hover:text-neutral-900" data-role="auth-me-link" style="display: none">
My dashboards
</a> <button type="button" class="text-neutral-600 hover:text-neutral-900 bg-transparent border-0 cursor-pointer p-0" data-role="auth-signin" style="display: none; font: inherit;">
Sign in
</button> <button type="button" class="text-neutral-600 hover:text-neutral-900 bg-transparent border-0 cursor-pointer p-0" data-role="auth-signout" style="display: none; font: inherit;">
Sign out
</button> </nav> </div> </header> <main class="flex-1"> ${renderSlot($$result, $$slots["default"])} </main> ${renderScript($$result, "C:/Users/Nemo/Documents/Coding/FinanceForDC/src/layouts/BaseLayout.astro?astro&type=script&index=0&lang.ts")} </body> </html>`;
}, "C:/Users/Nemo/Documents/Coding/FinanceForDC/src/layouts/BaseLayout.astro", void 0);

export { $$BaseLayout as $ };
