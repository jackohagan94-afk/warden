"""Guard against version drift between warden.__version__ and pyproject.

warden.__version__ (in warden/__init__.py) is the runtime/healthcheck version string;
pyproject's [project].version is the packaging version. They are independent literals,
and __init__ silently drifted to a stale 0.3.1 while pyproject moved to 0.4.x. This
test fails CI if a release bumps one and forgets the other.
"""

import tomllib
from pathlib import Path

import warden


def test_init_version_matches_pyproject() -> None:
    pyproject = Path(__file__).resolve().parent.parent / "pyproject.toml"
    data = tomllib.loads(pyproject.read_text(encoding="utf-8"))
    assert warden.__version__ == data["project"]["version"]
