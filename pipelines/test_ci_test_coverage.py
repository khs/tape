"""Meta-test: every pipelines/test_*.py must be wired into ci.yml.

CI runs the Python tests by ENUMERATING `python -m unittest pipelines.<name>`
rather than `unittest discover` (pipelines/ is a PEP-420 namespace package, which
discover refuses as a start dir). That's a footgun: a newly-added test_*.py
silently never runs in CI unless someone remembers to add it to the list — which
is exactly how test_census_acs_choropleth + test_fred_catalog sat un-run, and
the same class of gap that let a coverage failure hide until it broke a deploy.

This test closes the gap: it fails if any pipelines/test_*.py module name is
absent from .github/workflows/ci.yml, forcing the author to wire the new test in.
(It checks for the module name appearing anywhere in the file, so the existing
`python -m unittest pipelines.<name> -v` lines satisfy it.)
"""
from __future__ import annotations

import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
CI_YML = HERE.parent / ".github" / "workflows" / "ci.yml"


class CiTestCoverageTest(unittest.TestCase):
    def test_every_test_module_is_enumerated_in_ci(self) -> None:
        modules = sorted(p.stem for p in HERE.glob("test_*.py"))
        ci_text = CI_YML.read_text(encoding="utf-8")
        missing = [m for m in modules if f"pipelines.{m}" not in ci_text]
        self.assertFalse(
            missing,
            (
                "pipelines/test_*.py modules not enumerated in "
                ".github/workflows/ci.yml — they silently never run in CI. Add a "
                "`python -m unittest pipelines.<name> -v` line for each:\n  "
                + "\n  ".join(missing)
            ),
        )


if __name__ == "__main__":
    unittest.main()
