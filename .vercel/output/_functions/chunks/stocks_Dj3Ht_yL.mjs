import { n as createVNode, F as Fragment, az as __astro_tag_component__ } from './astro/server_DWURT7C5.mjs';
import 'clsx';

const frontmatter = {
  "title": "Stocks — famous names",
  "description": "KELLER WRITE THIS",
  "order": 7,
  "defaultDelta": "1m",
  "sections": [{
    "title": "Financials",
    "charts": ["stocks/brk_b", "stocks/jpm", "stocks/bac", "stocks/gs", "stocks/v", "stocks/ma"]
  }, {
    "title": "Healthcare",
    "charts": ["stocks/jnj", "stocks/unh", "stocks/lly", "stocks/pfe"]
  }, {
    "title": "Energy",
    "charts": ["stocks/xom", "stocks/cvx"]
  }, {
    "title": "Consumer",
    "charts": ["stocks/ko", "stocks/pep", "stocks/wmt", "stocks/cost", "stocks/hd", "stocks/mcd", "stocks/dis"]
  }, {
    "title": "Industrials & autos",
    "charts": ["stocks/ba", "stocks/cat", "stocks/ge", "stocks/tsla"]
  }, {
    "title": "Tech beyond the mega-caps",
    "charts": ["stocks/nflx", "stocks/asml", "stocks/tsm", "stocks/avgo", "stocks/orcl", "stocks/crm", "stocks/csco"]
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
const url = "src/content/dashboards/stocks.mdx";
const file = "C:/Users/Nemo/Documents/Coding/FinanceForDC/src/content/dashboards/stocks.mdx";
const Content = (props = {}) => MDXContent({
  ...props,
  components: { Fragment: Fragment, ...props.components, },
});
Content[Symbol.for('mdx-component')] = true;
Content[Symbol.for('astro.needsHeadRendering')] = !Boolean(frontmatter.layout);
Content.moduleId = "C:/Users/Nemo/Documents/Coding/FinanceForDC/src/content/dashboards/stocks.mdx";
__astro_tag_component__(Content, 'astro:jsx');

export { Content, Content as default, file, frontmatter, getHeadings, url };
