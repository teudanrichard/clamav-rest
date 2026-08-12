from __future__ import annotations

import subprocess
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
CHART = ROOT / "charts" / "clamav-rest"


def _render_chart() -> list[dict]:
    rendered = subprocess.run(
        ["helm", "template", "test", str(CHART)],
        check=True,
        capture_output=True,
        text=True,
    ).stdout
    return [document for document in yaml.safe_load_all(rendered) if document]


def test_each_service_selects_one_workload_with_matching_named_ports() -> None:
    documents = _render_chart()
    workloads = [document for document in documents if document["kind"] == "Deployment"]
    services = [document for document in documents if document["kind"] == "Service"]

    for service in services:
        selector = service["spec"]["selector"]
        matches = [
            workload
            for workload in workloads
            if selector.items() <= workload["spec"]["template"]["metadata"]["labels"].items()
        ]
        assert len(matches) == 1, (
            f"Service {service['metadata']['name']} selects {len(matches)} Deployments"
        )

        container_ports = {
            port.get("name")
            for container in matches[0]["spec"]["template"]["spec"]["containers"]
            for port in container.get("ports", [])
        }
        for service_port in service["spec"]["ports"]:
            target = service_port.get("targetPort", service_port["port"])
            if isinstance(target, str):
                assert target in container_ports
