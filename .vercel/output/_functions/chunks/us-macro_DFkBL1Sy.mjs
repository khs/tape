import { n as createVNode, F as Fragment, az as __astro_tag_component__ } from './astro/server_DWURT7C5.mjs';
import 'clsx';

const frontmatter = {
  "title": "US Macro snapshot",
  "description": "KELLER WRITE THIS",
  "order": 2,
  "defaultDelta": "1m",
  "sections": [{
    "title": "Treasuries & yield curve",
    "charts": ["us-macro/us_3mo", "us-macro/two_year", "us-macro/us_5y", "us-macro/ten_year", "us-macro/us_30y", "us-macro/curve_spread", "us-macro/fed_funds", "us-macro/mortgage_30y"]
  }, {
    "title": "Inflation",
    "charts": ["us-macro/cpi", "us-macro/core_cpi", "us-macro/headline_pce", "us-macro/core_pce"]
  }, {
    "title": "Labor",
    "charts": ["us-macro/unemployment", "us-macro/payrolls", "us-macro/labor_participation", "us-macro/avg_hourly_earnings"]
  }, {
    "title": "Output",
    "charts": ["us-macro/real_gdp", "us-macro/industrial_production", "us-macro/capacity_util"]
  }, {
    "title": "Spending & income",
    "charts": ["us-macro/retail_sales", "us-macro/personal_income", "us-macro/saving_rate"]
  }, {
    "title": "Housing",
    "charts": ["us-macro/housing_starts", "us-macro/case_shiller", "us-macro/median_home_price"]
  }, {
    "title": "Monetary & credit",
    "charts": ["us-macro/m2", "us-macro/fed_balance_sheet", "us-macro/hy_spread", "us-macro/ig_spread"]
  }, {
    "title": "Stocks & risk",
    "charts": ["us-macro/sp500", "us-macro/nasdaq", "us-macro/vix"]
  }, {
    "title": "Sentiment",
    "charts": ["us-macro/umich"]
  }]
};
function getHeadings() {
  return [];
}
function _createMdxContent(props) {
  const _components = {
    p: "p",
    ...props.components
  };
  return createVNode(_components.p, {
    children: "KELLER WRITE THIS"
  });
}
function MDXContent(props = {}) {
  const {wrapper: MDXLayout} = props.components || ({});
  return MDXLayout ? createVNode(MDXLayout, {
    ...props,
    children: createVNode(_createMdxContent, {
      ...props
    })
  }) : _createMdxContent(props);
}
const url = "src/content/dashboards/us-macro.mdx";
const file = "C:/Users/Nemo/Documents/Coding/FinanceForDC/src/content/dashboards/us-macro.mdx";
const Content = (props = {}) => MDXContent({
  ...props,
  components: { Fragment: Fragment, ...props.components, },
});
Content[Symbol.for('mdx-component')] = true;
Content[Symbol.for('astro.needsHeadRendering')] = !Boolean(frontmatter.layout);
Content.moduleId = "C:/Users/Nemo/Documents/Coding/FinanceForDC/src/content/dashboards/us-macro.mdx";
__astro_tag_component__(Content, 'astro:jsx');

export { Content, Content as default, file, frontmatter, getHeadings, url };
