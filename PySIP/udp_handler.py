import asyncio
import logging
from typing import Any
from .utils.logger import logger

class UdpHandler(asyncio.DatagramProtocol):
    def __init__(self) -> None:
        self.transport: asyncio.DatagramTransport = None
        self.data_q = asyncio.Queue()
        super().__init__()

    def connection_made(self, transport) -> None:
        self.transport = transport
        logger.log(logging.INFO, "Successful UDP connection has been made.")

    def connection_lost(self, exc: Exception | None) -> None:
        logger.log(logging.INFO, "UDP Connection has been lost")
        if self.transport:
            self.transport.close()

    def error_received(self, exc: Exception) -> None:
        logger.log(logging.ERROR, f"An error received: {exc}", exc_info=True)

    def send_message(self, message: bytes, address: tuple = None) -> None:
        if not self.transport:
            logger.log(logging.WARNING, "Unable to send message due to Transport closed")
            return
        self.transport.sendto(message)

    def datagram_received(self, data: bytes, addr: tuple[str | Any, int]) -> None:
        asyncio.ensure_future(self.data_q.put(data))

    async def read(self):
        return await self.data_q.get()


class UdpReader:
    def __init__(self, protocol: UdpHandler) -> None:
        self.protocol = protocol

    async def read(self, length: int = -1):
        return await self.protocol.read()


class UdpWriter:
    def __init__(self, protocol: UdpHandler) -> None:
        self.protocol = protocol

    async def write(self, data: bytes):
        self.protocol.send_message(data)

    def get_extra_info(self, name, default=None):
        if not self.protocol.transport:
            logger.log(logging.WARNING, "Can't invoke get_extra_info due to transport closed")
            return
        return self.protocol.transport.get_extra_info(name, default)


async def open_udp_connection(host: str, port: int):
    loop = asyncio.get_event_loop()
    transport, protocol = await loop.create_datagram_endpoint(
        lambda: UdpHandler(),
        remote_addr=(host, port)
    )
    reader = UdpReader(protocol)
    writer = UdpWriter(protocol)

    return reader, writer

