import asyncio
import struct

import pytest

from app.config import Settings
from app.socket_client import BackendSocketClient, ClamAVUnavailable, UploadTooLarge


class Writer:
    def __init__(self):
        self.data = bytearray()
        self.closed = False

    def write(self, data):
        self.data.extend(data)

    async def drain(self):
        pass

    def close(self):
        self.closed = True

    async def wait_closed(self):
        pass


@pytest.mark.asyncio
async def test_instream_protocol(monkeypatch):
    reader = object()
    writer = Writer()
    client = BackendSocketClient(Settings())

    async def connect():
        return reader, writer

    async def read(_):
        return "stream: OK"

    monkeypatch.setattr(client, "_connect", connect)
    monkeypatch.setattr(client, "_read", read)

    async def chunks():
        yield b"abc"
        yield b"de"

    result, size = await client.scan_stream(chunks(), 10)
    assert (result, size) == ("stream: OK", 5)
    assert writer.data == b"zINSTREAM\0" + struct.pack("!I", 3) + b"abc" + struct.pack(
        "!I", 2
    ) + b"de" + struct.pack("!I", 0)


@pytest.mark.asyncio
async def test_instream_rejects_large_upload(monkeypatch):
    writer = Writer()
    client = BackendSocketClient(Settings())

    async def connect():
        return object(), writer

    monkeypatch.setattr(client, "_connect", connect)

    async def chunks():
        yield b"12345"

    with pytest.raises(UploadTooLarge):
        await client.scan_stream(chunks(), 4)


@pytest.mark.asyncio
async def test_stream_cancellation_closes_socket(monkeypatch):
    writer = Writer()
    client = BackendSocketClient(Settings())

    async def connect():
        return object(), writer

    monkeypatch.setattr(client, "_connect", connect)

    async def chunks():
        yield b"started"
        await asyncio.sleep(60)

    task = asyncio.create_task(client.scan_stream(chunks(), 100))
    await asyncio.sleep(0)
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task
    assert writer.closed


@pytest.mark.asyncio
async def test_response_timeout_closes_socket(monkeypatch):
    writer = Writer()
    client = BackendSocketClient(Settings(socket_read_timeout=0.01))

    async def connect():
        return asyncio.StreamReader(), writer

    monkeypatch.setattr(client, "_connect", connect)
    with pytest.raises(ClamAVUnavailable, match="failed to read from ClamAV"):
        await client.ping()
    assert writer.closed


@pytest.mark.asyncio
async def test_partial_response_before_close_is_returned_for_protocol_validation():
    reader = asyncio.StreamReader()
    reader.feed_data(b"stream: truncated")
    reader.feed_eof()
    response = await BackendSocketClient(Settings())._read(reader)
    assert response == "stream: truncated"


@pytest.mark.asyncio
async def test_empty_response_is_unavailable():
    reader = asyncio.StreamReader()
    reader.feed_eof()
    with pytest.raises(ClamAVUnavailable, match="without a response"):
        await BackendSocketClient(Settings())._read(reader)
