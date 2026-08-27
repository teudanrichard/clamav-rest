import re
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
CHART = ROOT / "charts" / "clamav-rest"


def test_release_versions_are_consistent() -> None:
    version = (ROOT / "VERSION").read_text().strip()
    chart = yaml.safe_load((CHART / "Chart.yaml").read_text())

    assert re.fullmatch(r"\d+\.\d+\.\d+", version)
    assert chart["version"] == version
    assert str(chart["appVersion"]) == version


def test_chart_publication_waits_for_image_publication() -> None:
    workflow = yaml.safe_load((ROOT / ".github" / "workflows" / "ci.yml").read_text())
    needs = workflow["jobs"]["chart"]["needs"]

    assert "image-publish" in ([needs] if isinstance(needs, str) else needs)


def test_release_waits_for_image_and_chart_publication() -> None:
    workflow = yaml.safe_load((ROOT / ".github" / "workflows" / "ci.yml").read_text())
    needs = workflow["jobs"]["release"]["needs"]

    assert set(needs) == {"image-publish", "chart"}
