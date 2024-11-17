import asyncio
import logging
from typing import Callable, Dict, List
import uuid
import random

from PySIP.sip_call import SipCall

from .sip_core import SipCore, SipMessage, Counter
from .filters import SIPCompatibleMethods, SIPStatus, ConnectionType
from .utils.logger import logger
from .exceptions import NoPasswordFound


__all__ = ["SipClient"]


class SipClient:
    def __init__(
        self,
        username,
        server,
        connection_type: str,
        password: str,
        *,
        register_duration=600,
        caller_id="",
        sip_core=None,
    ):
        self.username = username
        try:
            self.server = server.split(":")[0]
            self.port = server.split(":")[1]
        except IndexError:
            self.port = 5060
        self.server = self.server + ":" + str(self.port)

        if password:
            self.password = password
        else:
            raise NoPasswordFound(
                "No password was provided please provide password to use for Digest auth."
            )

        self.CTS = "TLS" if "TLS" in connection_type else connection_type
        self.connection_type = ConnectionType(connection_type)
        self.reader, self.writer = None, None
        self.all_tasks: List[asyncio.Task] = []
        self.sip_core = (
            sip_core
            if sip_core is not None
            else SipCore(self.username, self.server, connection_type, password)
        )
        self.call_id = self.sip_core.gen_call_id()
        self.sip_core.on_message_callbacks.append(self.message_handler)
        self.register_counter = Counter(random.randint(1, 2000))
        self.register_tags = {"local_tag": "", "remote_tag": "", "type": "", "cseq": 0}
        self.registered = asyncio.Event()
        self.unregistered = asyncio.Event()
        self.register_duration = register_duration
        self.caller_id = caller_id if caller_id else username
        self.my_public_ip = None
        self.my_private_ip = None
        self._callbacks: Dict[str, List[Callable]] = {}

    async def run(self):
        register_task = None
        receive_task = None
        tasks = []
        try:
            self.my_public_ip = await asyncio.to_thread(self.sip_core.get_public_ip)
            self.my_private_ip = await asyncio.to_thread(self.sip_core.get_local_ip)

            if (
                not self.sip_core.is_running.is_set()
                and not self.sip_core._is_connecting.is_set()
            ):
                # only connect if it is not already connected
                await self.sip_core.connect()

            elif self.sip_core._is_connecting.is_set():
                await self.sip_core.is_running.wait()

            register_task = asyncio.create_task(
                self.periodic_register(self.register_duration), name="Periodic Register"
            )
            tasks.append(register_task)
            if not self.sip_core.receive_task:
                receive_task = asyncio.create_task(
                    self.sip_core.receive(), name="Receive Messages Task"
                )
                self.sip_core.receive_task = receive_task
                tasks.append(self.sip_core.receive_task)

            try:
                self.all_tasks.extend(tasks)
                self.registered.set()
                await asyncio.gather(*tasks)
            except asyncio.CancelledError:
                if receive_task.done():
                    pass
                if asyncio.current_task() and asyncio.current_task().cancelling() > 0:
                    raise

        except Exception as e:
            logger.log(logging.ERROR, e, exc_info=True)
            return

        finally:

            if register_task and not register_task.done():
                register_task.cancel()
                try:
                    await register_task
                except asyncio.CancelledError:
                    pass  # Task cancellation is expected

            if receive_task and not receive_task.done():
                receive_task.cancel()
                try:
                    await receive_task
                except asyncio.CancelledError:
                    pass  # Task cancellation is expected

    async def stop(self):
        unregister = self.build_register_message(unregister=True)
        await self.sip_core.send(unregister)
        try:
            await asyncio.wait_for(self.unregistered.wait(), 4)
            logger.log(
                logging.INFO,
                "Sip Account: %s has been de-registered from the server",
                self.username,
            )
        except asyncio.TimeoutError:
            logger.log(
                logging.WARNING, "Failed to de-register Sip Account: %s", self.username
            )

        self.sip_core.is_running.clear()
        await self.sip_core.close_connections()
        self.registered.clear()

    async def periodic_register(self, delay: float):
        while True:
            await self.register()

            sleep_task = asyncio.create_task(asyncio.sleep(delay - 5))
            event_cleared_task = asyncio.create_task(
                self.wait_for_event_clear(self.sip_core.is_running)
            )
            self.all_tasks.extend([sleep_task, event_cleared_task])

            _, pending = await asyncio.wait(
                [sleep_task, event_cleared_task], return_when="FIRST_COMPLETED"
            )

            for task in pending:
                task.cancel()

            if not self.sip_core.is_running.is_set():
                break

        logger.log(
            logging.DEBUG,
            "The app will no longer register. Registeration task stopped.",
        )

    async def wait_for_event_clear(self, event: asyncio.Event):
        while True:
            if not event.is_set():
                break

            await asyncio.sleep(0.1)

    async def check_connection_type(self):
        self.my_public_ip = await asyncio.to_thread(self.sip_core.get_public_ip)
        self.my_private_ip = await asyncio.to_thread(self.sip_core.get_local_ip)

        connection_types = [
            ConnectionType.UDP,
            ConnectionType.TCP,
            ConnectionType.TLS,
            ConnectionType.TLSv1,
        ]
        found_connections = [ConnectionType.UDP]
        found_connections.clear()

        for con in connection_types:
            self.sip_core.is_running.clear()
            self.sip_core.connection_type = con
            self.connection_type = con
            self.sip_core.port = (
                5061 if con in [ConnectionType.TLS, ConnectionType.TLSv1] else 5060
            )
            try:
                await self.sip_core.connect()
            except Exception:
                continue
            await self.register()

            reader = self.sip_core.udp_reader or self.sip_core.reader
            if not reader:
                return found_connections
            try:
                _ = await asyncio.wait_for(reader.read(), 1)
                found_connections.append(con)
            except asyncio.TimeoutError:
                continue
        return found_connections

    def build_register_message(
        self, auth=False, received_message=None, unregister=False
    ):
        # Generate unique identifiers for the message
        branch_id = str(uuid.uuid4()).upper()
        # Initialize transaction
        call_id = self.call_id

        # Start building the SIP message based on authentication need
        if auth:
            # Handling authenticated REGISTER request
            unregister = True if self.register_tags["type"] == "UNREGISTER" else False
            if not received_message:
                return
            nonce = received_message.nonce
            realm = received_message.realm
            cseq = next(self.register_counter)
            self.register_tags["cseq"] = cseq
            to_tag = self.register_tags["remote_tag"] = received_message.to_tag
            uri = f"sip:{self.server}:{self.port};transport={self.CTS}"
            response = self.sip_core.generate_response("REGISTER", nonce, realm, uri)

            # Adjust Via and Contact headers for public IP and port if available
            my_public_ip = self.my_public_ip
            ip = received_message.public_ip if not my_public_ip else my_public_ip
            port = received_message.rport
            from_tag = self.register_tags["local_tag"]
            expires = ";expires=0" if unregister else ""
            expires_field = "Expires: 60\r\n" if not unregister else ""

            # Construct the REGISTER request with Authorization header
            msg = (
                f"REGISTER sip:{self.server};transport={self.CTS} SIP/2.0\r\n"
                f"Via: SIP/2.0/{self.CTS} {ip}:{port};rport;branch={received_message.branch};alias\r\n"
                f"Max-Forwards: 70\r\n"
                f"From: <sip:{self.caller_id}@{self.server}>;tag={from_tag}\r\n"
                f"To: <sip:{self.username}@{self.server}>;tag={to_tag}\r\n"
                f"Call-ID: {call_id}\r\n"
                f"CSeq: {cseq} REGISTER\r\n"
                f"Contact: <sip:{self.username}@{ip}:{port};transport={self.CTS};ob>{expires}\r\n"
                f"{expires_field}"
                f'Authorization: Digest username="{self.username}", realm="{realm}", nonce="{nonce}", uri="{uri}", response="{response}", algorithm="MD5"\r\n'
                f"Content-Length: 0\r\n\r\n"
            )
        else:
            # Handling unauthenticated REGISTER request
            ip = self.my_private_ip
            port = self.port
            _, my_public_port = self.sip_core.get_extra_info("sockname")
            if not self.register_tags["local_tag"]:
                self.register_tags["local_tag"] = self.sip_core.generate_tag()

            cseq = next(self.register_counter)
            expires = ";expires=0" if unregister else ""
            expires_field = "Expires: 60\r\n" if not unregister else ""
            self.register_tags["type"] = "UNREGISTER" if unregister else "REGISTER"

            # Construct the REGISTER request without Authorization header
            msg = (
                f"REGISTER sip:{self.server};transport={self.CTS} SIP/2.0\r\n"
                f"Via: SIP/2.0/{self.CTS} {ip}:{my_public_port};rport;branch={branch_id};alias\r\n"
                f"Max-Forwards: 70\r\n"
                f"From: <sip:{self.caller_id}@{self.server}>;tag={self.register_tags['local_tag']}\r\n"
                f"To: <sip:{self.username}@{self.server}>\r\n"
                f"Call-ID: {call_id}\r\n"
                f"CSeq: {cseq} REGISTER\r\n"
                f"Contact: <sip:{self.username}@{self.my_public_ip}:{my_public_port};transport={self.CTS};ob>{expires}\r\n"
                f"{expires_field}"
                f"Content-Length: 0\r\n\r\n"
            )

        return msg

    def ok_generator(self, data_parsed: SipMessage):
        peer_ip, peer_port = self.sip_core.get_extra_info("peername")
        _, port = self.sip_core.get_extra_info("sockname")
        my_public_ip = self.my_public_ip

        msg = "SIP/2.0 200 OK\r\n"
        msg += f"Via: {data_parsed.get_header('Via')}\r\n"

        if data_parsed.method == "OPTIONS":
            to_tag = self.sip_core.generate_tag()
            msg += f"From: {data_parsed.get_header('From')}\r\n"
            msg += f"To: <sip:{self.username}@{my_public_ip}>;tag={to_tag}\r\n"
        else:
            msg += f"From: <sip:{self.username}@{self.server}>;tag={data_parsed.from_tag}\r\n"
            msg += (
                f"To: <sip:{self.username}@{self.server}>;tag={data_parsed.to_tag}\r\n"
            )

        msg += f"Call-ID: {data_parsed.call_id}\r\n"
        msg += f"CSeq: {data_parsed.cseq} {data_parsed.method}\r\n"
        msg += f"Contact: <sip:{self.username}@{my_public_ip}:{port};transport={self.CTS.upper()};ob>\r\n"
        msg += f"Allow: {', '.join(SIPCompatibleMethods)}\r\n"
        msg += "Supported: replaces, timer\r\n"
        msg += "Content-Length: 0\r\n\r\n"

        return msg

    async def ping(self):
        options_message = ""  # TODO Impmelement an options generator when required
        await self.sip_core.send(options_message)

    async def reregister(self, auth, data):
        msg = self.build_register_message(auth, data)

        await self.sip_core.send(msg)
        return

    async def register(self):
        msg = self.build_register_message()

        await self.sip_core.send(msg)
        return

    async def message_handler(self, msg: SipMessage):
        # This is the main message handler inside the class
        # its like other handlers outside the class that can
        # be accessed with @:meth:`Client.on_message` the only
        # difference is that its handled inside the :obj:`Client`
        # and it's onlt for developer's usage. unlike other handlers
        # it has no filters for now.
        print(msg.data)
        to = msg.get_header("To")
        if (
            not msg.call_id == self.call_id and self.username not in to
        ):  # Filter only current call
            return  # These are just for extra check and not necessary

        await asyncio.sleep(0.001)
        if msg.status == SIPStatus(401) and msg.method == "REGISTER":
            # This is the case when we have to send a retegister
            await self.reregister(True, msg)
            logger.log(logging.DEBUG, "Register message has been sent to the server")

        elif msg.status == SIPStatus(200) and msg.method == "REGISTER":
            # This is when we receive the response for the register
            logger.log(logging.DEBUG, "Successfully REGISTERED")

            # In case the response is of Un-register we set this
            if self.register_tags["type"] == "UNREGISTER":
                if msg.cseq == self.register_tags["cseq"]:
                    self.unregistered.set()

        elif msg.data.startswith(
            "OPTIONS"
        ):  # If we recieve PING then PONG incase of keep-alive required
            logger.log(
                logging.DEBUG, "Keep-alive message received from the server. sending OK"
            )
            options_ok = self.ok_generator(msg)
            await self.sip_core.send(options_ok)

        elif msg.data.startswith("INVITE") and self.username in to:
            incoming_call = SipCall(
                self.username, self.password, self.server, "", sip_core=self.sip_core
            )
            for cb in self._get_callbacks("incoming_call_cb"):
                incoming_call._register_callback("incoming_call_cb", cb)

            await incoming_call.handle_incoming_call(msg)

    def _register_callback(self, cb_type, cb):
        self._callbacks.setdefault(cb_type, []).append(cb)

    def _get_callbacks(self, cb_type):
        return self._callbacks.get(cb_type, [])

    def _remove_callback(self, cb_type, cb):
        callbacks = self._callbacks.get(cb_type, [])
        if cb in callbacks:
            callbacks.remove(cb)
