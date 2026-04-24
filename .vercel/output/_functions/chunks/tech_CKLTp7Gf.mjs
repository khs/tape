import { n as createVNode, F as Fragment, az as __astro_tag_component__ } from './astro/server_DWURT7C5.mjs';
import 'clsx';

const frontmatter = {
  "title": "Tech industry snapshot",
  "description": "KELLER WRITE THIS",
  "order": 3,
  "defaultDelta": "1m",
  "sections": [{
    "title": "Sector indices",
    "charts": ["tech/indices"]
  }, {
    "title": "Mega-caps",
    "charts": ["tech/aapl", "tech/msft", "tech/goog", "tech/amzn", "tech/meta", "tech/nvda"]
  }, {
    "title": "Credit",
    "charts": ["tech/hy_tmt_bonds"]
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
const url = "src/content/dashboards/tech.mdx";
const file = "C:/Users/Nemo/Documents/Coding/FinanceForDC/src/content/dashboards/tech.mdx";
const Content = (props = {}) => MDXContent({
  ...props,
  components: { Fragment: Fragment, ...props.components, },
});
Content[Symbol.for('mdx-component')] = true;
Content[Symbol.for('astro.needsHeadRendering')] = !Boolean(frontmatter.layout);
Content.moduleId = "C:/Users/Nemo/Documents/Coding/FinanceForDC/src/content/dashboards/tech.mdx";
__astro_tag_component__(Content, 'astro:jsx');

export { Content, Content as default, file, frontmatter, getHeadings, url };
