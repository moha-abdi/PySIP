import asyncio
import random
import traceback
from typing import Literal
import edge_tts
from edge_tts.communicate import uuid

from .sip_core import Counter, SipCore, SipDialogue, SipMessage
from .CustomCommuicate import CommWithPauses, NoPausesFound
from pydub import AudioSegment
import os
import janus

from .filters import SIPMessageType, SIPStatus, ConnectionType, CallState
from enum import Enum
from .rtp import PayloadType, RTPClient, TransmitType
from . import _print_debug_info
from .exceptions import SIPTransferException

__all__ = [
    'CallState',
    'CallStatus',
    'SipCall',
    'TTS'
]

class CallStatus(Enum):
    REGISTERING = "REGISTERING"
    REREGISTERING = "REREGISTERING"
    INVITING = "INVITING"
    REINVITING = "REINVITING"
    REGISTERED = "REGISTERED"
    INVITED = "INVITED"
    FAILED = "FAILED"
    INACTIVE = "INACTIVE"


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
        connection_type: Literal['TCP', 'UDP', 'TLS', 'TLSv1'] = 'UDP',
        caller_id: str = ""
    ) -> None:

        self.username = username
        self.route = route
        self.server = route.split(":")[0]
        self.port = int(route.split(":")[1])
        self.connection_type = connection_type
        self.password = password
        self.callee = callee
        self.sip_core = SipCore(self.username, route, connection_type, password)
        self.sip_core.on_message_callbacks.append(self.message_handler)
        self.call_id = self.sip_core.gen_call_id()
        self.cseq_counter = Counter(random.randint(1, 2000))
        self.CTS = 'TLS' if 'TLS' in connection_type else connection_type
        self.my_public_ip = self.sip_core.get_public_ip()
        self.my_private_ip = self.sip_core.get_local_ip()
        self.dialogue = SipDialogue(self.call_id, self.sip_core.generate_tag(), '')

    async def start(self):
        call_task = None
        receive_task = None
        try:
            await self.sip_core.connect() 
            receive_task = asyncio.create_task(self.sip_core.receive(), name='Receive Messages Task')
            call_task = asyncio.create_task(self.invite(), name='Call Initialization Task')
            try:
                await asyncio.gather(receive_task, call_task)
            except asyncio.CancelledError:
                if receive_task.done():
                    pass
                if asyncio.current_task() and asyncio.current_task().cancelling() > 0:
                    raise

        except Exception as e:
            print("Error: ", e)
            traceback.print_exc()
            return

        finally:
            
            if call_task and not call_task.done():
                call_task.cancel()
                try:
                    await call_task
                except asyncio.CancelledError:
                    pass  # Task cancellation is expected

            if receive_task and not receive_task.done():
                receive_task.cancel()
                try:
                    await receive_task
                except asyncio.CancelledError:
                    pass  # Task cancellation is expected

    async def stop(self, reason: str = "Normal Stop"):
        self.sip_core.is_running.clear()
        await self.sip_core.close_connections()
        _print_debug_info("Call terminated due to: ", reason)

    def generate_invite_message(self, auth=False, received_message=None):
        _, local_port = self.sip_core.get_extra_info('sockname')
        local_ip = self.my_public_ip  # Corrected the typo from 'puplic' to 'public'

        if auth and received_message:
            # Handling INVITE with authentication
            nonce, realm, ip, port = self.extract_auth_details(received_message)
            new_cseq = next(self.cseq_counter)
            uri = f'sip:{self.callee}@{self.server}:{self.port};transport={self.CTS}'
            auth_header = self.generate_auth_header("INVITE", uri, nonce, realm)
            return self.construct_invite_message(local_ip, local_port, new_cseq, auth_header, received_message)

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
        return (f'Authorization: Digest username="{self.username}", '
                f'realm="{realm}", nonce="{nonce}", uri="{uri}", '
                f'response="{response}", algorithm="MD5"\r\n')

    def construct_invite_message(self, ip, port, cseq, auth_header=None, received_message=None):
        # Common INVITE message components
        tag = self.dialogue.local_tag
        call_id = self.call_id
        branch_id = f"z9hG4bK-{str(uuid.uuid4())}"
        transaction = self.dialogue.add_transaction(branch_id, "INVITE")

        msg = (f"INVITE sip:{self.callee}@{self.server}:{self.port};transport={self.CTS} SIP/2.0\r\n"
               f"Via: SIP/2.0/{self.CTS} {ip}:{port};rport;branch={branch_id};alias\r\n"
               f"Max-Forwards: 70\r\n"
               f"From: <sip:{self.username}@{self.server}>;tag={tag}\r\n"
               f"To: <sip:{self.callee}@{self.server}>\r\n"
               f"Call-ID: {call_id}\r\n"
               f"CSeq: {transaction.cseq} INVITE\r\n"
               f"Contact: <sip:{self.username}@{ip}:{port};transport={self.CTS};ob>\r\n"
               "Content-Type: application/sdp\r\n")

        # Addang the Authorization header if auth is required
        if auth_header:
            msg += auth_header

        body = SipMessage.generate_sdp(ip)  # Assuming this method generates the SDP body
        msg += f"Content-Length: {len(body.encode())}\r\n\r\n{body}"

        return msg

    def ack_generator(self, transaction):
        _, port = self.sip_core.get_extra_info('sockname')
        ip = self.my_public_ip

        msg = f"ACK sip:{self.callee}@{self.server}:{self.port};transport={self.CTS} SIP/2.0\r\n"
        msg += f"Via: SIP/2.0/{self.CTS} {ip}:{port};rport;branch={transaction.branch_id};alias\r\n"
        msg += f"Max-Forwards: 70\r\n"
        msg += f"From: sip:{self.username}@{self.server};tag={self.dialogue.local_tag}\r\n"
        msg += f"To: sip:{self.callee}@{self.server};tag={self.dialogue.remote_tag}\r\n"
        msg += f"Call-ID: {self.call_id}\r\n"
        msg += f"CSeq: {transaction.cseq} ACK\r\n"
        msg += f"Route: <sip:{self.server}:{self.port};transport={self.CTS};lr>\r\n"
        msg += f"Content-Length:  0\r\n\r\n"

        return msg

    async def message_handler(self, msg: SipMessage):
        # In call events Handling
        
        #If the call id is not same as the current then return
        if msg.call_id != self.call_id:
            return

        if msg.status == SIPStatus(401) and msg.method == "INVITE":
            # Handling the auth of the invite
            self.dialogue.remote_tag = msg.to_tag or ''
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
            self.dialogue.auth_retry_count += 1
            _print_debug_info("INVITED")

        elif msg.status == SIPStatus(200) and msg.method == "INVITE":
            # Handling successfull invite response 
            self.dialogue.remote_tag = msg.to_tag or '' # setting it if not set
            _print_debug_info("RE-INVITED")
            transaction = self.dialogue.add_transaction(self.sip_core.gen_branch(), "ACK")
            ack_message = self.ack_generator(transaction)
            self.dialogue.auth_retry_count = 0 # reset the auth counter
            await self.sip_core.send(ack_message)

        elif str(msg.status).startswith('1') and msg.method == "INVITE":
            # Handling 1xx profissional responses
            self.dialogue.remote_tag = msg.to_tag or '' # setting it if not already
            self.dialogue.auth_retry_count = 0 # reset the auth counter
            pass

        # Finally update status and fire events
        self.dialogue.update_state(msg)


    async def reinvite(self, auth, msg):
        reinvite_msg = self.generate_invite_message(auth, msg)
        await self.sip_core.send(reinvite_msg)
        return

    async def invite(self):
        msg = self.generate_invite_message()
        self.last_invite_msg = msg

        await self.sip_core.send(msg)
        return


class TTS:
    def __init__(
        self,
        text: str,
        voice: str,
        output_filename: str
    ) -> None:

        self.text = text
        self.voice = voice
        self.output_filename = output_filename

    async def generate_audio(self) -> str:
        try:
            communicate = CommWithPauses(self.text, self.voice)
            await communicate.save(self.output_filename)
        except NoPausesFound:
            communicate = edge_tts.Communicate(self.text, self.voice)
            await communicate.save(self.output_filename)

        file_name = self.convert_to_wav()
        self.cleanup()

        return file_name

    def convert_to_wav(self):
        sound: AudioSegment = AudioSegment.from_mp3(self.output_filename)
        wav_filename = os.path.splitext(self.output_filename)[0] + ".wav"
        sound.export(wav_filename, format='wav')

        return wav_filename

    def cleanup(self):
        os.remove(self.output_filename)


class DTMFHandler:
    def __init__(self) -> None:
        self.queue: janus.Queue[str] = janus.Queue()
        self.dtmf_queue = asyncio.Queue()
        self.started_typing_event = asyncio.Event()
        self.dtmf_codes = []

    def dtmf_callback(self, code: str) -> None:
        self.queue.sync_q.put(code)
        self.dtmf_codes.append(code)

    async def started_typing(self, event):
        await self.started_typing_event.wait()
        await event()

    async def get_dtmf(self, length=1, finish_on_key=None) -> str:
        dtmf_codes = []

        if finish_on_key:
            while True:
                code = await self.queue.async_q.get()
                self.queue.async_q.task_done()
                if dtmf_codes and code == finish_on_key:
                    break
                dtmf_codes.append(code)
                if not self.started_typing_event.is_set():
                    self.started_typing_event.set()

        else:
            for _ in range(length):
                code = await self.queue.async_q.get()
                self.queue.async_q.task_done()
                dtmf_codes.append(code)
                if not self.started_typing_event.is_set():
                    self.started_typing_event.set()

        self.started_typing_event.clear()
        return ''.join(dtmf_codes)




