import ast
import re
import runpy
from pathlib import Path

import pytest
from panel.io.convert import WEB_WORKER_TEMPLATE


replace_library_with_url = runpy.run_path(
    str(Path(__file__).resolve().parents[2] / "src" / "webapp_build_utils.py")
)["replace_library_with_url"]


def test_local_wheels_are_used_in_both_panel_install_attempts():
    requirements = "'brimfile[export-tiff]>=1.7.6', 'brimview_widgets', 'bokeh==3.10.2'"
    worker = WEB_WORKER_TEMPLATE.render(
        env_spec=requirements,
        fallback_env_spec=requirements,
        code="",
        PYODIDE_URL="",
    )
    worker = replace_library_with_url(worker, "brimview_widgets", "js.toAbsoluteUrl('./widgets.whl')")
    worker = replace_library_with_url(worker, "brimfile", "js.toAbsoluteUrl('./brimfile.whl')")

    installs = re.findall(r"await\s+micropip\.install\((\[.*?\])\)", worker)
    assert len(installs) == 2
    for install in installs:
        expressions = ast.parse(install, mode="eval").body.elts
        assert [ast.unparse(expression) for expression in expressions] == [
            "js.toAbsoluteUrl('./brimfile.whl')",
            "js.toAbsoluteUrl('./widgets.whl')",
            "'bokeh==3.10.2'",
        ]


def test_missing_package_in_fallback_fails_the_build():
    worker = "await micropip.install(['brimfile'])\nawait micropip.install(['other'])"
    with pytest.raises(ValueError, match="Library 'brimfile' not found"):
        replace_library_with_url(worker, "brimfile", "js.toAbsoluteUrl('./brimfile.whl')")


def test_missing_install_fails_the_build():
    with pytest.raises(ValueError, match="micropip install"):
        replace_library_with_url("no install here", "brimfile", "js.toAbsoluteUrl('./brimfile.whl')")