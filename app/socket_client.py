"""Asynchronous client for the clamd protocol."""

import asyncio
import struct
from collections.abc import AsyncIterable

from app.config import Settings


class ClamAVError(RuntimeError):
    pass


class ClamAVUnavailable(ClamAVError):
    pass


class UploadTooLarge(ValueError):
    pass


class BackendSocketClient:
    """Use an isolated socket per command, allowing safe concurrent requests."""

    def __init__(self, settings: Settings) -> None:
        self.settings = settings

    async def _connect(self) -> tuple[asyncio.StreamReader, asyncio.StreamWriter]:
        try:
            connection = (
                asyncio.open_unix_connection(self.settings.backend_socket_path)
                if self.settings.backend_socket_path
                else asyncio.open_connection(self.settings.backend_host, self.settings.backend_port)
            )
            return await asyncio.wait_for(connection, self.settings.socket_connect_timeout)
        except (TimeoutError, OSError) as exc:
            raise ClamAVUnavailable(f"unable to connect to ClamAV: {exc}") from exc

    async def _read(self, reader: asyncio.StreamReader) -> str:
        try:
            data = await asyncio.wait_for(
                reader.readuntil(b"\0"), self.settings.socket_read_timeout
            )
        except asyncio.IncompleteReadError as exc:
            if not exc.partial:
                raise ClamAVUnavailable("ClamAV closed the connection without a response") from exc
            data = exc.partial
        except (TimeoutError, OSError) as exc:
            raise ClamAVUnavailable(f"failed to read from ClamAV: {exc}") from exc
        return data.rstrip(b"\0\r\n").decode(errors="replace")

    async def command(self, command: str) -> str:
        reader, writer = await self._connect()
        try:
            writer.write(f"z{command}\0".encode("ascii"))
            await writer.drain()
            return await self._read(reader)
        except OSError as exc:
            raise ClamAVUnavailable(f"failed to write to ClamAV: {exc}") from exc
        finally:
            writer.close()
            try:
                await writer.wait_closed()
            except OSError:
                pass

    async def ping(self) -> str:
        return await self.command("PING")

    async def version(self) -> str:
        return await self.command("VERSION")

    async def scan_stream(self, chunks: AsyncIterable[bytes], max_bytes: int) -> tuple[str, int]:
        reader, writer = await self._connect()
        size = 0
        try:
            writer.write(b"zINSTREAM\0")
            async for chunk in chunks:
                if not chunk:
                    continue
                size += len(chunk)
                if size > max_bytes:
                    raise UploadTooLarge(f"file exceeds the {max_bytes}-byte upload limit")
                writer.write(struct.pack("!I", len(chunk)))
                writer.write(chunk)
                await writer.drain()
            writer.write(struct.pack("!I", 0))
            await writer.drain()
            return await self._read(reader), size
        except OSError as exc:
            raise ClamAVUnavailable(f"failed to stream to ClamAV: {exc}") from exc
        finally:
            writer.close()
            try:
                await writer.wait_closed()
            except OSError:
                pass
