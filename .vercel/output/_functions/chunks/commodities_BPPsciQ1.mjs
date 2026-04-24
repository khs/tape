import { n as createVNode, F as Fragment, az as __astro_tag_component__ } from './astro/server_DWURT7C5.mjs';
import 'clsx';

const frontmatter = {
  "title": "Commodities",
  "description": "KELLER WRITE THIS",
  "order": 5,
  "defaultDelta": "1m",
  "sections": [{
    "title": "Precious metals",
    "charts": ["commodities/gold_futures", "commodities/silver_futures", "commodities/platinum_futures", "commodities/palladium_futures", "commodities/gld", "commodities/slv"]
  }, {
    "title": "Base metals",
    "charts": ["commodities/copper_futures"]
  }, {
    "title": "Energy",
    "charts": ["oil/wti", "oil/brent", "oil/nat_gas", "oil/rbob_wholesale", "oil/heating_oil_wholesale"]
  }, {
    "title": "Agricultural",
    "charts": ["commodities/corn_futures", "commodities/wheat_futures", "commodities/soybean_futures", "commodities/coffee_futures", "commodities/sugar_futures", "commodities/cotton_futures", "commodities/cocoa_futures", "commodities/cattle_futures", "commodities/orange_juice_futures", "commodities/lumber_futures"]
  }, {
    "title": "Broad-commodity ETFs",
    "charts": ["commodities/dbc", "commodities/gsg", "commodities/dba"]
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
const url = "src/content/dashboards/commodities.mdx";
const file = "C:/Users/Nemo/Documents/Coding/FinanceForDC/src/content/dashboards/commodities.mdx";
const Content = (props = {}) => MDXContent({
  ...props,
  components: { Fragment: Fragment, ...props.components, },
});
Content[Symbol.for('mdx-component')] = true;
Content[Symbol.for('astro.needsHeadRendering')] = !Boolean(frontmatter.layout);
Content.moduleId = "C:/Users/Nemo/Documents/Coding/FinanceForDC/src/content/dashboards/commodities.mdx";
__astro_tag_component__(Content, 'astro:jsx');

export { Content, Content as default, file, frontmatter, getHeadings, url };
