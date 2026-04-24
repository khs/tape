const contentModules = new Map([
["src/content/dashboards/commodities.mdx", () => import('./commodities_B2KEPiKy.mjs')],
["src/content/dashboards/markets.mdx", () => import('./markets_BW01m159.mjs')],
["src/content/dashboards/stocks.mdx", () => import('./stocks_DWQP0Cba.mjs')],
["src/content/dashboards/oil-energy.mdx", () => import('./oil-energy_BprpCbqD.mjs')],
["src/content/dashboards/countries.mdx", () => import('./countries_uv-AMARl.mjs')],
["src/content/dashboards/tech.mdx", () => import('./tech_BqHdTRBV.mjs')],
["src/content/dashboards/us-macro.mdx", () => import('./us-macro_BCIbN65H.mjs')]]);

export { contentModules as default };
