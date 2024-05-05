import asyncio
from concurrent.futures import ThreadPoolExecutor
import logging
from typing import List, Literal, Optional

from .utils.logger import logger
from .filters import ConnectionType
from .sip_call import SipCall
from .sip_client import SipClient
from .sip_core import SipCore, connection_ports


class SipAccount:
    """A wrapper class for `SipClient` and `SipCall`"""

    def __init__(
        self,
        username: str,
        password: str,
        hostname: str,
        *,
        connection_type: Literal["AUTO", "TCP", "UDP", "TLS", "TLSv1"] = "AUTO",
        caller_id=None,
        register_duration=600,
        max_ongoing_calls=10,
    ) -> None:
        self.username = username
        self.password = password
        self.caller_id = caller_id
        self.MAX_ONGOING_CALLS = max_ongoing_calls
        self.connection_type = connection_type
        self.hostname, self.port = self.__parse_hostname(hostname, connection_type)
        self.register_duration = register_duration
        self.__client_task = None
        self.__sip_client = None
        self.__calls: List[SipCall] = []
        if self.connection_type == "AUTO":
            self.__setup_connection_type()

        self.sip_core: Optional[SipCore] = SipCore(
            self.username, self.hostname, self.connection_type, password
        )

    def __parse_hostname(self, hostname: str, connection_type):
        try:
            _port = hostname.split(":")[1]
            port = int(_port)
        except IndexError:
            if connection_type != "AUTO":
                con_port = connection_ports.get(ConnectionType(connection_type))
                if not con_port:
                    port = None
                port = con_port
                hostname = hostname + ":" + str(port)
            else:
                port = None
        return hostname, port

    def __setup_connection_type(self):
        with ThreadPoolExecutor() as exe:
            result = exe.submit(asyncio.run, self._get_connection_type())
            self.connection_type = result.result()

    async def _get_connection_type(self):
        logger.log(
            logging.INFO,
            "Detecting connection type (UDP/TCP/TLS). This might take some time...",
        )
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
            caller_id=self.caller_id or "",
            sip_core=self.sip_core,
        )
        if (
            self.sip_core
            and not self.sip_core.is_running.is_set()
            and not self.sip_core._is_connecting.is_set()
        ):
            await self.sip_core.connect()
        self.__client_task = asyncio.create_task(self.__sip_client.run())
        try:
            await asyncio.wait_for(self.__sip_client.registered.wait(), 4)
            logger.log(
                logging.INFO, f"Sip Account: {self.username} registered to the server."
            )
        except asyncio.TimeoutError:
            logger.log(
                logging.WARNING,
                f"Failed register Sip Account: {self.username}.",
            )

    async def unregister(self):
        if self.__sip_client and self.__sip_client.registered.is_set():
            await self.__sip_client.stop()

    def make_call(self, to: str) -> SipCall:
        if not self.__sip_client:
            self.sip_core = None
        if ongoing_calls := len(self.__calls) >= self.MAX_ONGOING_CALLS:
            raise RuntimeError(
                f"Maximum allowed concurrent calls ({ongoing_calls}) reached."
            )
        if self.connection_type == "AUTO":
            raise RuntimeError("Connection type not found")

        __sip_call = SipCall(
            self.username,
            self.password,
            self.hostname,
            to,
            caller_id=self.caller_id or "",
            sip_core=self.sip_core,
        )
        self.__calls.append(__sip_call)
        return __sip_call

    def remove_call(self, call: SipCall):
        try:
            self.__calls.remove(call)
        except ValueError:
            pass
