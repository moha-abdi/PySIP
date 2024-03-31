import asyncio
import logging
from typing import List, Literal, Optional

from .utils.logger import logger
from .filters import ConnectionType
from .sip_call import SipCall
from .sip_client import SipClient
from .sip_core import connection_ports


class SipAccount:
    """A wrapper class for `SipClient` and `SipCall`"""

    def __init__(
        self,
        username: str,
        password: str,
        hostname: str,
        *,
        connection_type: Literal["AUTO", "TCP", "UDP", "TLS", "TLSv1"] = "AUTO",
        register_duration=600,
        max_ongoing_calls=10,
        loop: Optional[asyncio.AbstractEventLoop] = None,
    ) -> None:
        self.username = username
        self.password = password
        self.MAX_ONGOING_CALLS = max_ongoing_calls
        self.hostname, self.port = self.__parse_hostname(hostname, connection_type)
        self.connection_type = connection_type
        self.register_duration = register_duration
        self.__client_task = None
        self.__sip_client = None
        self.__calls: List[SipCall] = []
        self.__loop = loop

    def __parse_hostname(self, hostname: str, connection_type):
        try:
            _port = hostname.split(":")[1]
            port = int(_port)
        except IndexError:
            if connection_type != "AUTO":
                con_port = connection_ports.get(ConnectionType(self.connection_type))
                if not con_port:
                    port = None
                port = con_port
                hostname = hostname + ":" + str(port)
            else:
                port = None
        return hostname, port

    async def _get_connection_type(self):
        logger.log(logging.INFO, "Detecting connection type (UDP/TCP/TLS). This might take some time...")
        self.__sip_client = SipClient(
            self.username,
            self.hostname,
            "UDP",
            self.password,
            register_duration=self.register_duration,
        )
        con_type = await self.__sip_client.check_connection_type()
        if not con_type:
            raise ConnectionError(
                "Failed to Auto-Detect connection type. Please provide it manually"
            )

        self.port = connection_ports.get(con_type[0])
        self.hostname = self.hostname.split(":")[0] + ":" + str(self.port)
        logger.log(logging.INFO, "Connection type detected: %s", con_type[0])
        return con_type[0]

    async def register(self):
        if self.connection_type == "AUTO":
            self.connection_type = await self._get_connection_type()

        self.__sip_client = SipClient(
            self.username,
            self.hostname,
            str(self.connection_type),
            self.password,
            register_duration=self.register_duration,
        )
        self.__client_task = asyncio.create_task(self.__sip_client.run())

    def register_sync(self):
        if self.__loop is None:
            raise RuntimeError("There is no event loop provided")

        if self.connection_type == "AUTO":
            self.connection_type = self.__loop.run_until_complete(
                self._get_connection_type()
            )

        self.__sip_client = SipClient(
            self.username,
            self.hostname,
            str(self.connection_type),
            self.password,
            register_duration=self.register_duration,
        )
        self.__client_task = self.__loop.create_task(self.__sip_client.run())

    async def unregister(self):
        if self.__sip_client:
            await self.__sip_client.stop()

    def unregister_sync(self):
        if self.__loop is None:
            raise RuntimeError("There is no event loop provided")

        if self.__sip_client:
            self.__loop.run_until_complete(self.__sip_client.stop())

        if self.__client_task:
            self.__client_task.cancel()

            try:
                self.__loop.run_until_complete(self.__client_task)
            except asyncio.CancelledError:
                pass

        # Cancel all remaining tasks in the event loop
        pending_tasks = [
            task
            for task in (self.__sip_client.all_tasks if self.__sip_client else [])
            if not task.done()
        ]

        for task in pending_tasks:
            task.cancel()

        # Wait for all tasks to complete or be cancelled :)
        self.__loop.run_until_complete(
            asyncio.gather(*pending_tasks, return_exceptions=True)
        ) 

    def make_call(self, to: str, caller_id: str = "") -> SipCall:
        if ongoing_calls := len(self.__calls) >= self.MAX_ONGOING_CALLS:
            raise RuntimeError(
                f"Maximum allowed concurrent calls ({ongoing_calls}) reached."
            )
        if self.connection_type == "AUTO":
            self.connection_type = asyncio.run(
                self._get_connection_type()
            )

        __sip_call = SipCall(
            self.username, self.password, self.hostname, to, caller_id=caller_id
        )
        self.__calls.append(__sip_call)
        return __sip_call

    def remove_call(self, call: SipCall):
        try:
            self.__calls.remove(call)
        except ValueError:
            pass
