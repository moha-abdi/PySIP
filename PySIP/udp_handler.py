import asyncio
from typing import Any


class UdpHandler(asyncio.DatagramProtocol):
    def __init__(self) -> None:
        self.transport = None
        self.data_q =asyncio.Queue()
        super().__init__()

    def connection_made(self, transport: asyncio.DatagramTransport) -> None:
        print("Successful UDP connection has been made.")
        self.transport = transport  # Store the transport for later use

    def connection_lost(self, exc: Exception | None) -> None:
        print("Connection has been lost")
        if self.transport:
            self.transport.close()

    def error_received(self, exc: Exception) -> None:
        print("There was an error: ", exc)

    def send_message(self, message: bytes, address: tuple = None) -> None:
        self.transport.sendto(message)
        # print(f"Message '{message.decode()}' sent to {address}")

    def datagram_received(self, data: bytes, addr: tuple[str | Any, int]) -> None:
        asyncio.ensure_future(self.data_q.put(data))
        # print('Received: ', data.decode())

    async def read(self):
        return await self.data_q.get()



class UdpReader:
    def __init__(self, protocol: asyncio.DatagramProtocol) -> None:
        self.protocol = protocol

    async def read(self, length: int = -1):
        await self.protocol.read()


class UdpWriter:
    def __init__(self, protocol: asyncio.DatagramProtocol) -> None:
        self.protocol = protocol

    async def write(self, data: bytes) -> None:
        self.protocol.send_message(data)


async def open_udp_connection(host: str, port: int):
    loop = asyncio.get_event_loop()
    transport, protocol = await loop.create_datagram_endpoint(
        lambda: UdpHandler(),
        remote_addr=(host, port)
    )
    reader = UdpReader(protocol)
    writer = UdpWriter(protocol)

    return reader, writer

