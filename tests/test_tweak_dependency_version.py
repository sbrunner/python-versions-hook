from pathlib import Path

import multi_repo_automation as mra

from python_versions_hook import _tweak_dependency_version


def test_tweak_dependency_version_add():
    with mra.EditTOML(Path(__file__).parent / "test_data" / "test_pyproject.toml") as edit:
        _tweak_dependency_version(edit)

        assert edit["project"]["optional-dependencies"]["extra"] == ["pkg_in_extra==1.2.3"]
        assert set(edit["project"]["dependencies"]) == set(
            [
                "pkg_only==2.3.4",
                "pkg_major<2,>=1",
                "pkg_minor<1.3,>=1.2",
                "pkg_patch<1.2.4,>=1.2.3",
                "pkg_patch_error==1.2",
                "pkg_present",
                "pkg_no==1.2.3",
                "pkg_extra[extra]==1.2.3",
                "pkg_set<3.0.0,>=1.0.0",
            ]
        )
