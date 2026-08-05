"""Opt-in tests against a real ClamAV daemon."""

import os

import pytest

from app.config import Settings
from app.socket_client import BackendSocketClient

pytestmark = pytest.mark.skipif(
    os.getenv("RUN_CLAMAV_INTEGRATION") != "1", reason="real ClamAV integration is opt-in"
)


async def _one_chunk(data: bytes):
    yield data


@pytest.mark.asyncio
async def test_real_clamav_clean_and_eicar_scans():
    client = BackendSocketClient(Settings())
    assert await client.ping() == "PONG"

    clean, clean_size = await client.scan_stream(_one_chunk(b"production readiness"), 1024)
    assert clean.endswith(" OK")
    assert clean_size == 20

    eicar = b"X5O!P%@AP[4\\PZX54(P^)7CC)7}$EICAR-STANDARD-ANTIVIRUS-TEST-FILE!$H+H*"
    infected, infected_size = await client.scan_stream(_one_chunk(eicar), 1024)
    assert infected.endswith(" FOUND")
    assert "Eicar" in infected
    assert infected_size == len(eicar)
