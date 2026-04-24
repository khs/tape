import { n as createVNode, F as Fragment, az as __astro_tag_component__ } from './astro/server_DWURT7C5.mjs';
import 'clsx';

const frontmatter = {
  "title": "Oil & Energy",
  "description": "KELLER WRITE THIS",
  "order": 1,
  "defaultDelta": "1m",
  "sections": [{
    "title": "Crude oil",
    "charts": ["oil/wti", "oil/brent"]
  }, {
    "title": "Refined products",
    "charts": ["oil/rbob_wholesale", "oil/heating_oil_wholesale", "oil/retail_gasoline", "oil/retail_diesel"]
  }, {
    "title": "Natural gas",
    "charts": ["oil/nat_gas"]
  }, {
    "title": "Sector equities",
    "charts": ["oil/xle", "oil/transition"]
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
const url = "src/content/dashboards/oil-energy.mdx";
const file = "C:/Users/Nemo/Documents/Coding/FinanceForDC/src/content/dashboards/oil-energy.mdx";
const Content = (props = {}) => MDXContent({
  ...props,
  components: { Fragment: Fragment, ...props.components, },
});
Content[Symbol.for('mdx-component')] = true;
Content[Symbol.for('astro.needsHeadRendering')] = !Boolean(frontmatter.layout);
Content.moduleId = "C:/Users/Nemo/Documents/Coding/FinanceForDC/src/content/dashboards/oil-energy.mdx";
__astro_tag_component__(Content, 'astro:jsx');

export { Content, Content as default, file, frontmatter, getHeadings, url };
