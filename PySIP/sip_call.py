import asyncio
from collections import namedtuple
from functools import wraps
import logging
import random
from typing import Callable, Dict, List, Literal, Optional
import wave

from .call_handler import CallHandler
from .exceptions import SIPTransferException
from .rtp_handler import RTP_PORT_RANGE, RTPClient, TransmitType
from .sip_core import Counter, DialogState, SipCore, SipDialogue, SipMessage
from .filters import SIPCompatibleMethods, SIPStatus, CallState
from .utils.logger import logger, get_call_logger
from .codecs import CODECS

__all__ = ["SipCall", "DTMFHandler"]


class SipCall:
    """
    Represents a VoIP call using SIP protocol.

    Args:
        username (str): SIP username.
        route (str): SIP server route.
        password (str, optional): Authentication password.
        device_id (str, optional): Calling device ID.
        tts (bool, optional): Enable Text-to-Speech.
        text (str, optional): TTS text.

    Methods:
        :meth:`on_message()`: Start listening for SIP messages.
        :meth:`signal_handler()`: Handle signals during the call.
        :meth:`call(callee: str | int)`: Initiate a call.

    Example:
        voip_call = SipCall(username='user', route='server:port', password='pass')
        voip_call.call('11234567890')
    """

    def __init__(
        self,
        username: str,
        password: str,
        route: str,
        callee: str,
        *,
        connection_type: Literal["TCP", "UDP", "TLS", "TLSv1"] = "UDP",
        caller_id: str = "",
    ) -> None:
        self.username = username
        self.caller_id = username if not caller_id else caller_id
        self.route = route
        self.server = route.split(":")[0]
        self.port = int(route.split(":")[1])
        self.connection_type = connection_type
        self.password = password
        self.callee = callee
        self.sip_core = SipCore(self.username, route, connection_type, password)
        self.sip_core.on_message_callbacks.append(self.message_handler)
        self.sip_core.on_message_callbacks.append(self.error_handler)
        self._callbacks: Dict[str, List[Callable]] = {}
        self.call_id = self.sip_core.gen_call_id()
        self.cseq_counter = Counter(random.randint(1, 2000))
        self.CTS = "TLS" if "TLS" in connection_type else connection_type
        self.my_public_ip = None
        self.my_private_ip = None
        self._rtp_session: Optional[RTPClient] = None
        self._call_handler = CallHandler(self)
        self._dtmf_handler = DTMFHandler()
        self._refer_future: asyncio.Future = asyncio.Future()
        self.__recorded_audio_bytes: Optional[bytes] = None
        self.__is_call_stopped = False
        self.dialogue = SipDialogue(self.call_id, self.sip_core.generate_tag(), "")
        self.call_state = CallState.INITIALIZING

    async def start(self):
        _tasks = []
        try:
            self.my_public_ip = await asyncio.to_thread(self.sip_core.get_public_ip)
            self.my_private_ip = await asyncio.to_thread(self.sip_core.get_local_ip)
            self.setup_local_session()
            self.dialogue.username = self.username
            await self.sip_core.connect()
            # regiser the callback for when the call is ANSWERED
            self._register_callback("state_changed_cb", self.on_call_answered)
            self._register_callback("dtmf_callback", self._dtmf_handler.dtmf_callback)
            receive_task = asyncio.create_task(
                self.sip_core.receive(), name="Receive Messages Task"
            )
            call_task = asyncio.create_task(
                self.invite(), name="Call Initialization Task"
            )
            call_handler_task = asyncio.create_task(
                self.call_handler.send_handler(), name="Calld Handler Task"
            )
            _tasks.extend([receive_task, call_task, call_handler_task])
            try:
                await asyncio.gather(*_tasks, return_exceptions=False)
            except asyncio.CancelledError:
                _task = asyncio.current_task()
                if _task and _task.cancelling() > 0:
                    raise

        except Exception as e:
            logger.log(logging.ERROR, e, exc_info=True)
            return

        finally:
            for _task in _tasks:
                if _task.done():
                    continue
                _task.cancel()
                try:
                    await _task
                except asyncio.CancelledError:
                    pass

    async def stop(self, reason: str = "Normal Stop"):
        # we have to handle three different scenarious when hanged-up
        # 1st its if the state was in predialog state, in this scenarious
        # we just close connections and thats all.
        # 2nd scenario is if the state is initial meaning the dialog is
        # established but not yet confirmed, thus we send cancel.
        # 3rd scenario is if the state is confirmed meaning the call was
        # asnwered and in this scenario we send bye.
        if self.__is_call_stopped:
            logger.log(
                logging.WARNING,
                "The call was already TERMINATED. stop call invoked more than once.",
            )
            return

        if self.dialogue.state == DialogState.PREDIALOG:
            self.sip_core.is_running.clear()
            await self.sip_core.close_connections()
            logger.info("The call has ben stopped")

        elif (self.dialogue.state == DialogState.INITIAL) or (
            self.dialogue.state == DialogState.EARLY
        ):
            # not that this will cancel using the latest transaction
            transaction = self.dialogue.transactions[-1]
            cancel_message = self.cancel_generator(transaction)
            await self.sip_core.send(cancel_message)
            try:
                await asyncio.wait_for(
                    self.dialogue.events[DialogState.TERMINATED].wait(), timeout=5
                )
                logger.log(logging.DEBUG, "The call has been cancelled")
            except asyncio.TimeoutError:
                logger.log(logging.WARNING, "The call has been cancelled with errors")
            finally:
                self.sip_core.is_running.clear()
                await self.sip_core.close_connections()

        elif self.dialogue.state == DialogState.CONFIRMED:
            bye_message = self.bye_generator()
            await self.sip_core.send(bye_message)
            try:
                await asyncio.wait_for(
                    self.dialogue.events[DialogState.TERMINATED].wait(), timeout=5
                )
                logger.log(logging.INFO, "The call has been hanged up")
            except asyncio.TimeoutError:
                logger.log(logging.WARNING, "The call has been hanged up with errors")
            finally:
                self.sip_core.is_running.clear()
                await self.sip_core.close_connections()

        elif self.dialogue.state == DialogState.TERMINATED:
            self.sip_core.is_running.clear()
            await self.sip_core.close_connections() 

        # finally notify the callbacks
        for cb in self._get_callbacks("hanged_up_cb"):
            logger.log(logging.DEBUG, f"The call has been hanged up due to: {reason}")
            await cb(reason)
        logger.log(logging.INFO, "Call hanged up due to: %s", reason)

        # also check for any rtp session and stop it
        await self._cleanup_rtp()
        self.__is_call_stopped = True

    async def _cleanup_rtp(self):
        if not self._rtp_session:
            return

        if not self._rtp_session._rtp_task:
            return

        await self._rtp_session._stop()
        await self._rtp_session._wait_stopped()
        logger.log(logging.DEBUG, "Cleaning up the rtp..")

        _rtp_task = self._rtp_session._rtp_task
        try:
            await _rtp_task
        except asyncio.CancelledError:
            pass
        except Exception as e:
            logger.log(logging.ERROR, f"Couldn't cleanup RTP: {e}")

    async def _wait_stopped(self):
        while True:
            if not self.sip_core.is_running.is_set():
                if self.call_state is CallState.INITIALIZING:
                    await asyncio.sleep(0.2)
                    continue
                break

            await asyncio.sleep(0.2)

    def setup_local_session(self):
        sdp = SipMessage.generate_sdp(
            self.sip_core.get_local_ip(),
            random.choice(RTP_PORT_RANGE),
            random.getrandbits(32),
            CODECS,
        )
        sdp = SipMessage.parse_sdp(SipMessage.sdp_to_dict(sdp))
        self.dialogue._local_session_info = sdp

    def generate_invite_message(self, auth=False, received_message=None):
        _, local_port = self.sip_core.get_extra_info("sockname")
        local_ip = self.my_public_ip  # Corrected the typo from 'puplic' to 'public'

        if auth and received_message:
            # Handling INVITE with authentication
            nonce, realm, ip, port = self.extract_auth_details(received_message)
            new_cseq = next(self.cseq_counter)
            uri = f"sip:{self.callee}@{self.server}:{self.port};transport={self.CTS}"
            auth_header = self.generate_auth_header("INVITE", uri, nonce, realm)
            return self.construct_invite_message(
                local_ip, local_port, new_cseq, auth_header, received_message
            )

        else:
            # Initial INVITE without authentication
            new_cseq = next(self.cseq_counter)
            return self.construct_invite_message(local_ip, local_port, new_cseq)

    def extract_auth_details(self, received_message):
        nonce = received_message.nonce
        realm = received_message.realm
        ip = received_message.public_ip
        port = received_message.rport
        return nonce, realm, ip, port

    def generate_auth_header(self, method, uri, nonce, realm):
        response = self.sip_core.generate_response(method, nonce, realm, uri)
        return (
            f'Authorization: Digest username="{self.username}", '
            f'realm="{realm}", nonce="{nonce}", uri="{uri}", '
            f'response="{response}", algorithm="MD5"\r\n'
        )

    def construct_invite_message(
        self, ip, port, cseq, auth_header=None, received_message=None
    ):
        # Common INVITE message components
        tag = self.dialogue.local_tag
        call_id = self.call_id
        branch_id = self.sip_core.gen_branch()
        transaction = self.dialogue.add_transaction(branch_id, "INVITE")

        msg = (
            f"INVITE sip:{self.callee}@{self.server}:{self.port};transport={self.CTS} SIP/2.0\r\n"
            f"Via: SIP/2.0/{self.CTS} {ip}:{port};rport;branch={branch_id};alias\r\n"
            f"Max-Forwards: 70\r\n"
            f"From: <sip:{self.caller_id}@{self.server}>;tag={tag}\r\n"
            f"To: sip:{self.callee}@{self.server}\r\n"
            f"Call-ID: {call_id}\r\n"
            f"CSeq: {transaction.cseq} INVITE\r\n"
            f"Contact: <sip:{self.username}@{ip}:{port};transport={self.CTS}>;expires=3600\r\n"
            f"Allow: {', '.join(SIPCompatibleMethods)}\r\n"
            "Supported: replaces, timer\r\n"
            "Content-Type: application/sdp\r\n"
        )

        # Addang the Authorization header if auth is required
        if auth_header:
            msg += auth_header

        body = str(self.dialogue.local_session_info)
        msg += f"Content-Length: {len(body.encode())}\r\n\r\n{body}"

        return msg

    def ack_generator(self, transaction):
        _, port = self.sip_core.get_extra_info("sockname")
        ip = self.my_public_ip

        msg = f"ACK sip:{self.callee}@{self.server}:{self.port};transport={self.CTS} SIP/2.0\r\n"
        msg += f"Via: SIP/2.0/{self.CTS} {ip}:{port};rport;branch={transaction.branch_id};alias\r\n"
        msg += "Max-Forwards: 70\r\n"
        msg += (
            f"From: sip:{self.caller_id}@{self.server};tag={self.dialogue.local_tag}\r\n"
        )
        msg += f"To: sip:{self.callee}@{self.server};tag={self.dialogue.remote_tag}\r\n"
        msg += f"Call-ID: {self.call_id}\r\n"
        msg += f"CSeq: {transaction.cseq} ACK\r\n"
        msg += f"Route: <sip:{self.server}:{self.port};transport={self.CTS};lr>\r\n"
        msg += "Content-Length: 0\r\n\r\n"

        return msg

    def bye_generator(self):
        peer_ip, peer_port = self.sip_core.get_extra_info("peername")
        _, port = self.sip_core.get_extra_info("sockname")

        branch_id = self.sip_core.gen_branch()
        transaction = self.dialogue.add_transaction(branch_id, "BYE")

        msg = f"BYE sip:{self.callee}@{peer_ip}:{peer_port};transport={self.CTS} SIP/2.0\r\n"
        msg += (
            f"Via: SIP/2.0/{self.CTS} {self.my_public_ip}:{port};rport;"
            + f"branch={branch_id};alias\r\n"
        )
        msg += 'Reason: Q.850;cause=16;text="normal call clearing"'
        msg += "Max-Forwards: 70\r\n"
        msg += (
            f"From: sip:{self.caller_id}@{self.server};tag={self.dialogue.local_tag}\r\n"
        )
        msg += f"To: sip:{self.callee}@{self.server};tag={self.dialogue.remote_tag}\r\n"
        msg += f"Call-ID: {self.call_id}\r\n"
        msg += f"CSeq: {transaction.cseq} BYE\r\n"
        msg += "Content-Length: 0\r\n\r\n"

        return msg

    def refer_generator(self, refer_to_callee):
        _, port = self.sip_core.get_extra_info("sockname")
        ip = self.my_public_ip

        branch_id = self.sip_core.gen_branch()
        transaction = self.dialogue.add_transaction(branch_id, "REFER")
        refer_to = f"sip:{refer_to_callee}@{self.server};transport={self.CTS}"
        referred_by = f"sip:{self.caller_id}@{self.server}"

        msg = f"REFER sip:{self.callee}@{self.server}:{self.port};transport={self.CTS} sip/2.0\r\n"
        msg += f"Via: sip/2.0/{self.CTS} {ip}:{port};rport;branch={branch_id};alias\r\n"
        msg += "Max-Forwards: 70\r\n"
        msg += (
            f"From: sip:{self.caller_id}@{self.server};tag={self.dialogue.local_tag}\r\n"
        )
        msg += f"To: sip:{self.callee}@{self.server};tag={self.dialogue.remote_tag}\r\n"
        msg += f"Call-ID: {self.call_id}\r\n"
        msg += f"CSeq: {transaction.cseq} REFER\r\n"
        msg += f"Refer-To: {refer_to}\r\n"
        msg += f"Referred-By: {referred_by}\r\n"
        msg += f"Contact: <sip:{self.username}@{ip}:{port};transport={self.CTS};ob>\r\n"
        msg += "Content-Length: 0\r\n\r\n"

        return msg

    def cancel_generator(self, transaction):
        _, port = self.sip_core.get_extra_info("sockname")
        ip = self.my_public_ip

        msg = f"CANCEL sip:{self.callee}@{self.server}:{self.port};transport={self.CTS} SIP/2.0\r\n"
        msg += (
            f"Via: SIP/2.0/{self.CTS} {ip}:{port};"
            + f"rport;branch={transaction.branch_id};alias\r\n"
        )
        msg += "Max-Forwards: 70\r\n"
        msg += (
            f"From:sip:{self.caller_id}@{self.server};tag={self.dialogue.local_tag}\r\n"
        )
        msg += f"To: sip:{self.callee}@{self.server}\r\n"
        msg += f"Call-ID: {self.call_id}\r\n"
        msg += f"CSeq: {transaction.cseq} CANCEL\r\n"
        msg += "Content-Length: 0\r\n\r\n"

        return msg

    def ok_generator(self, data_parsed: SipMessage):
        peer_ip, peer_port = self.sip_core.get_extra_info("peername")
        _, port = self.sip_core.get_extra_info("sockname")

        if data_parsed.is_from_client(self.username):
            from_header = f"From: <sip:{self.caller_id}@{self.server}>;tag={self.dialogue.local_tag}\r\n"
            to_header = f"To: <sip:{self.callee}@{self.server}>;tag={self.dialogue.remote_tag}\r\n"
        else:
            from_header = f"From: <sip:{self.callee}@{self.server}>;tag={self.dialogue.remote_tag}\r\n"
            to_header = f"To: <sip:{self.caller_id}@{self.server}>;tag={self.dialogue.local_tag}\r\n"

        msg = "SIP/2.0 200 OK\r\n"
        msg += "Via: " + data_parsed.get_header("Via") + "\r\n"
        msg += from_header
        msg += to_header
        msg += f"Call-ID: {data_parsed.call_id}\r\n"
        msg += f"CSeq: {data_parsed.cseq} {data_parsed.method}\r\n"
        msg += f"Contact: <sip:{self.username}@{self.my_public_ip}:{port};transport={self.CTS.upper()};ob>\r\n"
        msg += f"Allow: {', '.join(SIPCompatibleMethods)}\r\n"
        msg += "Supported: replaces, timer\r\n"
        msg += "Content-Length: 0\r\n\r\n"

        return msg

    async def message_handler(self, msg: SipMessage):
        # In call events Handling

        # If the call id is not same as the current then return
        if msg.call_id != self.call_id:
            return

        if msg.status == SIPStatus(401) and msg.method == "INVITE":
            # Handling the auth of the invite
            self.dialogue.remote_tag = msg.to_tag or ""
            transaction = self.dialogue.find_transaction(msg.branch)
            if not transaction:
                return
            ack_message = self.ack_generator(transaction)
            await self.sip_core.send(ack_message)

            if self.dialogue.auth_retry_count > self.dialogue.AUTH_RETRY_MAX:
                await self.stop("Unable to authenticate, check details")
                return
            # Then send reinvite with Authorization
            await self.reinvite(True, msg)
            await self.update_call_state(CallState.DAILING)
            self.dialogue.auth_retry_count += 1
            logger.log(logging.DEBUG, "Sent INVITE request to the server")

        elif msg.status == SIPStatus(200) and msg.method == "INVITE":
            # Handling successfull invite response
            self.dialogue.remote_tag = msg.to_tag or ""  # setting it if not set
            logger.log(logging.DEBUG, "INVITE Successfull, dialog is established.")
            transaction = self.dialogue.add_transaction(
                self.sip_core.gen_branch(), "ACK"
            )
            ack_message = self.ack_generator(transaction)
            self.dialogue.auth_retry_count = 0  # reset the auth counter
            await self.sip_core.send(ack_message)
            self.dialogue.update_state(msg)
            await self.update_call_state(CallState.ANSWERED)
            return

        elif str(msg.status).startswith("1") and msg.method == "INVITE":
            # Handling 1xx profissional responses
            st = (
                CallState.RINGING if msg.status is SIPStatus(180) else CallState.DAILING
            )
            await self.update_call_state(st)
            self.dialogue.remote_tag = msg.to_tag or ""  # setting it if not already
            self.dialogue.auth_retry_count = 0  # reset the auth counter
            pass

        elif msg.method == "BYE" and not msg.is_from_client(self.username):
            # Hanlding callee call hangup
            await self.update_call_state(CallState.ENDED)
            if not str(msg.data).startswith("BYE"):
                # Seperating BYE messges from 200 OK to bye messages or etc.
                self.dialogue.update_state(msg)
                return
            ok_message = self.ok_generator(msg)
            await self.sip_core.send(ok_message)
            await self.stop("Callee hanged up")

        elif msg.method == "BYE" and msg.is_from_client(self.username):
            await self.update_call_state(CallState.ENDED)

        elif msg.status == SIPStatus(487) and msg.method == "INVITE":
            transaction = self.dialogue.find_transaction(msg.branch)
            if not transaction:
                return
            ack_message = self.ack_generator(transaction)
            await self.sip_core.send(ack_message)
            await self.update_call_state(CallState.FAILED)

        elif str(msg.status).startswith("2") and msg.method == "REFER":
            SIPTransferResult = namedtuple("SIPTransferResult", ["code", "description"])
            if not self._refer_future.done():
                description = "Success"
                self._refer_future.set_result(
                    SIPTransferResult(int(msg.status or 0), description)
                )

        elif str(msg.status).startswith(("4", "5", "6")) and msg.method == "REFER":
            if not self._refer_future.done():
                description = (
                    "Client Error"
                    if str(msg.status).startswith("4")
                    else "Server Error"
                )
        
                self._refer_future.set_exception(
                    SIPTransferException(int(msg.status or -1), description)
                )

        elif str(msg.data).startswith("NOTIFY"):
            if msg.body_data:
                _data = msg.body_data.split(' ')
                logger.log(
                    logging.DEBUG, "Transfer status: %s",
                    ' '.join(_data[2:]).replace('\r\n', '')
                )
                for _cb in self._get_callbacks("transfer_cb"):
                    await _cb(SIPStatus(int(_data[1])))

            message = self.ok_generator(msg)
            await self.sip_core.send(message) 

        # Finally update status and fire events
        self.dialogue.update_state(msg)

    async def error_handler(self, msg: SipMessage):
        if not msg.status:
            return
        
        if not self.dialogue.remote_tag:
            self.dialogue.remote_tag = msg.to_tag or ""

        if not 400 <= msg.status.code <= 699:
            return

        if msg.status in [SIPStatus(401), SIPStatus(487)]:
            return

        if msg.status in [SIPStatus(486), SIPStatus(600), SIPStatus(603)]:
            # handle if busy
            transaction = self.dialogue.find_transaction(msg.branch)
            if not transaction:
                return
            ack_message = self.ack_generator(transaction)
            await self.sip_core.send(ack_message)
            # set the diologue state to TERMINATED and close
            self.dialogue.state = DialogState.TERMINATED
            self.dialogue.update_state(msg)
            await self.update_call_state(CallState.BUSY)
            if msg.status:
                await self.stop(msg.status.phrase)
            else:
                await self.stop()

        else:
            # for all other errors just send ack
            transaction = self.dialogue.find_transaction(msg.branch)
            if not transaction:
                return
            ack_message = self.ack_generator(transaction)
            await self.sip_core.send(ack_message)

            if msg.status in [SIPStatus.REQUEST_PENDING]:
                return
            # set the diologue state to TERMINATED and close
            self.dialogue.state = DialogState.TERMINATED
            self.dialogue.update_state(msg)
            await self.update_call_state(CallState.FAILED)
            if msg.status:
                await self.stop(msg.status.phrase)
            else:
                await self.stop()

    async def reinvite(self, auth, msg):
        reinvite_msg = await asyncio.to_thread(self.generate_invite_message, auth, msg)
        await self.sip_core.send(reinvite_msg)
        return

    async def invite(self):
        msg = await asyncio.to_thread(self.generate_invite_message)
        self.last_invite_msg = msg

        await self.sip_core.send(msg)
        return

    async def update_call_state(self, new_state):
        if new_state == self.call_state:
            return

        for cb in self._get_callbacks("state_changed_cb"):
            await cb(new_state)

        self.call_state = new_state
        logger.log(logging.DEBUG, f"Call state changed to -> {new_state}")

    def _register_callback(self, cb_type, cb):
        self._callbacks.setdefault(cb_type, []).append(cb)

    def _get_callbacks(self, cb_type):
        return self._callbacks.get(cb_type, [])

    def _remove_callback(self, cb_type, cb):
        callbacks = self._callbacks.get(cb_type, [])
        if cb in callbacks:
            callbacks.remove(cb)

    def on_call_hanged_up(self, func):
        @wraps(func)
        async def wrapper(reason: str):
            return await func(reason)

        self._register_callback("hanged_up_cb", wrapper)
        return wrapper

    def on_call_state_changed(self, func):
        @wraps(func)
        async def wrapper(new_state):
            return await func(new_state)

        self._register_callback("state_changed_cb", wrapper)
        return wrapper

    async def on_call_answered(self, state: CallState):
        if state is CallState.ANSWERED:
            # set-up RTP connections
            if not self.dialogue.local_session_info:
                logger.log(logging.CRITICAL, "No local session info defined")
                await self.stop()
                return
            elif not self.dialogue.remote_session_info:
                logger.log(logging.CRITICAL, "No remote session info defined")
                await self.stop()
                return

            local_sdp = self.dialogue.local_session_info
            remote_sdp = self.dialogue.remote_session_info
            self._rtp_session = RTPClient(
                remote_sdp.rtpmap,
                local_sdp.ip_address,
                local_sdp.port,
                remote_sdp.ip_address,
                remote_sdp.port,
                TransmitType.SENDRECV,
                local_sdp.ssrc,
                self._callbacks,
            )
            # start the session
            _rtp_task = asyncio.create_task(self._rtp_session._start())
            self._rtp_session._rtp_task = _rtp_task
            self._register_callback("dtmf_handler", self._dtmf_handler.dtmf_callback)
            logger.log(logging.DEBUG, "Done spawned _rtp_task in the background")

    def on_frame_received(self, func):
        @wraps(func)
        async def wrapper(frame):
            return await func(frame)

        self._register_callback("frame_monitor", wrapper)
        return wrapper

    def on_dtmf_received(self, func):
        @wraps(func)
        async def wrapper(dtmf_key):
            return await func(dtmf_key)

        self._register_callback("dtmf_callback", wrapper)
        return wrapper

    def on_amd_state_received(self, func):
        @wraps(func)
        async def wrapper(amd_state):
            return await func(amd_state)

        self._register_callback("amd_app", wrapper)
        return wrapper

    def on_transfer_state_changed(self, func):
        @wraps(func)
        async def wrapper(status: SIPStatus):
            return await func(status)

        self._register_callback("transfer_cb", wrapper)
        return

    @property
    def call_handler(self) -> CallHandler:
        return self._call_handler

    @call_handler.setter
    def call_handler(self, call_handler: CallHandler):
        self._call_handler = call_handler

    def process_recorded_audio(self) -> bytes:
        """Unpacks the recorded audio queue and make into bytes array"""
        audio_bytes = bytearray()
        if not self._rtp_session:
            logger.log(
                logging.WARNING,
                "Can not get recorded audio as there is no established session",
            )
            return bytes(audio_bytes)

        while True:
            try:
                if not (queue := self._rtp_session._output_queues.get("audio_record")):
                    break
                if not (frame := queue.get_nowait()):
                    break
                audio_bytes.extend(frame)
            except asyncio.QueueEmpty:
                break
        return bytes(audio_bytes)
    
    def get_recorded_audio(self, filename: Optional[str] = None, format="wav"):
        loop = asyncio.get_event_loop()
        loop.run_in_executor(None, self.__get_recorded_audio, filename, format)

    def __get_recorded_audio(self, filename: Optional[str] = None, format="wav"):
        """Only wav format supported currently the others wil be added"""
        if not self._rtp_session:
            logger.log(
                logging.WARNING,
                "Can not get recorded audio as there is no established session",
            )
            return
        if self.__recorded_audio_bytes is None:
            self.__recorded_audio_bytes = self.process_recorded_audio()

        filename = f'call_{self.call_id}.wav' if not filename else filename
        with wave.open(filename, "wb") as f:
            f.setsampwidth(2)
            f.setframerate(8000)
            f.setnchannels(1)

            f.writeframes(self.__recorded_audio_bytes)

    @property
    def recorded_audio_raw(self):
        if self.__recorded_audio_bytes is None:
            self.__recorded_audio_bytes = self.process_recorded_audio()

        return self.__recorded_audio_bytes


class DTMFHandler:
    def __init__(self) -> None:
        self.queue: asyncio.Queue = asyncio.Queue()
        self.dtmf_queue: asyncio.Queue = asyncio.Queue()
        self.started_typing_event = asyncio.Event()
        self.dtmf_codes: List[str] = []

    async def dtmf_callback(self, code: str) -> None:
        await self.queue.put(code)
        self.dtmf_codes.append(code)

    async def started_typing(self, event, *args):
        await self.started_typing_event.wait()
        self.started_typing_event.clear()
        event(*args)

    async def get_dtmf(self, length=1, finish_on_key=None) -> str:
        dtmf_codes: List[str] = []

        if finish_on_key:
            while True:
                code = await self.queue.get()
                if dtmf_codes and code == finish_on_key:
                    break
                dtmf_codes.append(code)
                if not self.started_typing_event.is_set():
                    self.started_typing_event.set()

        else:
            for _ in range(length):
                code = await self.queue.get()
                dtmf_codes.append(code)
                if not self.started_typing_event.is_set():
                    self.started_typing_event.set()

        self.started_typing_event.clear()
        return "".join(dtmf_codes)
