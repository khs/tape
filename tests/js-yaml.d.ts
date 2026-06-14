// Minimal ambient types for js-yaml (no @types/js-yaml installed; the .mjs
// build scripts import it untyped, but the typechecked test helpers need a
// declaration). Only the surface the corpus helpers use.
declare module "js-yaml" {
  export function load(input: string): unknown;
  const jsYaml: { load(input: string): unknown };
  export default jsYaml;
}
