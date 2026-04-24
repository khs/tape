import { n as createVNode, F as Fragment, az as __astro_tag_component__ } from './astro/server_DC5FRKA8.mjs';
import 'clsx';

const frontmatter = {
  "title": "Markets overview",
  "description": "KELLER WRITE THIS",
  "order": 6,
  "defaultDelta": "1m",
  "sections": [{
    "title": "Major US indices",
    "charts": ["markets/sp500", "markets/nasdaq", "markets/dia", "markets/iwm", "markets/iwb", "markets/vti"]
  }, {
    "title": "International",
    "charts": ["markets/efa", "markets/vea", "markets/eem", "markets/vwo"]
  }, {
    "title": "Sectors (S&P 500 SPDRs)",
    "charts": ["markets/xlk", "markets/xlf", "markets/xlv", "markets/xli", "markets/xlp", "markets/xly", "markets/xlb", "markets/xlc", "markets/xlre", "markets/xlu", "markets/xle"]
  }, {
    "title": "Risk",
    "charts": ["us-macro/vix"]
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
const url = "src/content/dashboards/markets.mdx";
const file = "C:/Users/Nemo/Documents/Coding/FinanceForDC/src/content/dashboards/markets.mdx";
const Content = (props = {}) => MDXContent({
  ...props,
  components: { Fragment: Fragment, ...props.components, },
});
Content[Symbol.for('mdx-component')] = true;
Content[Symbol.for('astro.needsHeadRendering')] = !Boolean(frontmatter.layout);
Content.moduleId = "C:/Users/Nemo/Documents/Coding/FinanceForDC/src/content/dashboards/markets.mdx";
__astro_tag_component__(Content, 'astro:jsx');

export { Content, Content as default, file, frontmatter, getHeadings, url };
