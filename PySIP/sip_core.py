import logging
import re
import random
import asyncio
from functools import wraps
import socket
import ssl
import uuid
import hashlib
from typing import Callable, List, Optional
import base64
import hmac
import time
import requests

from .utils.logger import logger
from .filters import (
    SipFilter,
    SIPMessageType,
    SIPCompatibleMethods,
    SIPCompatibleVersions,
    SIPStatus,
    ConnectionType,
)
from .udp_handler import open_udp_connection
from .exceptions import NoPasswordFound
from .codecs.codec_info import CodecInfo
from enum import Enum, auto


class DialogState(Enum):
    PREDIALOG = (
        auto()
    )  # Custom state meaning before auth is finished, as we inclided it in the dialog
    INITIAL = auto()  # Before receiving any provisional response
    EARLY = (
        auto()
    )  # After receiving a provisional response but before the final response
    CONFIRMED = auto()  # After receiving a final response
    TERMINATED = auto()  # After the dialog has end_of_headers


class DTMFMode(Enum):
    RFC_2833 = auto()
    INBAND = auto()
    AUTO = auto()


connection_ports = {
    ConnectionType.UDP: 5060,
    ConnectionType.TCP: 5060,
    ConnectionType.TLS: 5061,
    ConnectionType.TLSv1: 5061,
}

SAVE_TLS_KEYLOG = False
CHECKSUM_SALT = "oYRFBHVG31444fs45AWcvir_7%8mdtTUiujnduI134RGubctsb87654"


class SipCore:
    def __init__(self, username, server, connection_type: str, password: str):
        self.username = username
        self.server = server.split(":")[0]
        self.port = server.split(":")[1]
        self.connection_type = ConnectionType(connection_type)
        if password:
            self.password = password
        else:
            raise NoPasswordFound(
                "No password was provided please provide password to use for Digest auth."
            )

        self.on_message_callbacks: List[Callable] = []
        self.tags: List[str] = []
        self.is_running = asyncio.Event()
        self._is_connecting = asyncio.Event()
        self.reader, self.writer = None, None
        self.udp_reader, self.udp_writer = None, None
        self.receive_task: Optional[asyncio.Task] = None

    def get_public_ip(self) -> str | None:
        try:
            external_ip = requests.get(
                "https://api64.ipify.org?format=json", timeout=8
            ).json()["ip"]
        except requests.exceptions.Timeout:
            external_ip = None

        return external_ip

    def get_local_ip(self):
        try:
            # Create a socket object
            s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            # Connect the socket to a remote server
            # Here, '8.8.8.8' is the Google Public DNS, and '80' is the port number.
            s.connect(("8.8.8.8", 80))
            # Get the local IP address the socket is connected with
            ip = s.getsockname()[0]
            # Close the socket
            s.close()
        except Exception as e:
            logger.log(logging.CRITICAL, "The local IP address couldn't be retreived.")
            raise e
        return ip

    def get_extra_info(self, name: str):
        if self.connection_type == ConnectionType.UDP:
            if not self.udp_writer:
                raise ValueError("No UdpWriter")
            peer_info = self.udp_writer.get_extra_info(name)
            if peer_info:
                peer_ip, peer_port = peer_info
                return (peer_ip, peer_port)
            raise ValueError("No peer info")

        else:
            if not self.writer:
                raise ValueError("No StreamWriter")
            peer_ip, peer_port = self.writer.get_extra_info(name)
            return (peer_ip, peer_port)

    def generate_tag(self):
        tag = str(uuid.uuid4()).upper()
        if tag not in self.tags:
            self.tags.append(tag)
            return tag
        return ""

    def generate_urn_uuid(self):
        return str(uuid.uuid4()).upper()

    def gen_call_id(self) -> str:
        call_id = str(uuid.uuid4()).upper()
        return call_id

    def gen_urn_uuid(self) -> str:
        """
        Generate client instance specific urn:uuid
        """
        return str(uuid.uuid4())

    def gen_branch(self):
        return f"z9hG4bK-{str(uuid.uuid4())}"

    def generate_response(
        self, method, nonce, realm, uri, qop=None, nc=None, cnonce=None
    ):
        A1_string = self.username + ":" + realm + ":" + self.password
        A1_hash = hashlib.md5(A1_string.encode()).hexdigest()
        A2_string = (method + ":" + uri).encode()
        A2_hash = hashlib.md5(A2_string).hexdigest()

        if qop == "auth":
            response_string = (
                f"{A1_hash}:{nonce}:{nc}:{cnonce}:{qop}:{A2_hash}"
            ).encode()
        else:
            response_string = (A1_hash + ":" + nonce + ":" + A2_hash).encode()

        response_hash = hashlib.md5(response_string).hexdigest()
        return response_hash

    @staticmethod
    def generate_response_new(username, password, method, nonce, realm, uri):
        A1_string = username + ":" + realm + ":" + password
        A1_hash = hashlib.md5(A1_string.encode()).hexdigest()

        A2_string = (method + ":" + uri).encode()
        A2_hash = hashlib.md5(A2_string).hexdigest()

        response_string = (A1_hash + ":" + nonce + ":" + A2_hash).encode()
        response_hash = hashlib.md5(response_string).hexdigest()

        return response_hash

    def generate_checksum(self, method: str, username: str):
        timestamp = str(int(time.time() * 1000))
        salt = CHECKSUM_SALT.encode()
        message = (method + username + "@" + self.server + timestamp).encode()

        message_hash = hmac.new(salt, message, hashlib.sha512).digest()
        hashb64 = base64.b64encode(message_hash).decode()

        return Checksum(hashb64, timestamp)

    async def connect(self):
        self.is_running = asyncio.Event()
        self._is_connecting = asyncio.Event()
        try:
            self._is_connecting.set()
            if self.connection_type == ConnectionType.TCP:
                self.reader, self.writer = await asyncio.open_connection(
                    self.server,
                    self.port,
                )
                self.is_running.set()

            elif self.connection_type == ConnectionType.UDP:

                self.udp_reader, self.udp_writer = await open_udp_connection(
                    (self.server, self.port)
                )
                self.is_running.set()

            elif self.connection_type == ConnectionType.TLS:
                ssl_context = ssl.create_default_context(ssl.Purpose.CLIENT_AUTH)
                if SAVE_TLS_KEYLOG:
                    ssl_context.keylog_filename = "tls_keylog.log"
                self.reader, self.writer = await asyncio.open_connection(
                    self.server, self.port, ssl=ssl_context
                )
                self.is_running.set()

            elif self.connection_type == ConnectionType.TLSv1:
                ssl_context = ssl.SSLContext(ssl.PROTOCOL_TLSv1)
                ssl_context.set_ciphers("DEFAULT@SECLEVEL=1")
                if SAVE_TLS_KEYLOG:
                    ssl_context.keylog_filename = "tls_keylog.log"
                self.reader, self.writer = await asyncio.open_connection(
                    self.server, self.port, ssl=ssl_context
                )
                self.is_running.set()

        except (OSError, ssl.SSLError) as e:
            logger.log(logging.DEBUG, f"Error during connection: {e}")
            raise
            # Handle the error as needed
        except Exception as e:
            logger.log(logging.DEBUG, f"Unexpected Error: {e}")
            raise
        except asyncio.CancelledError:
            logger.log(logging.DEBUG, "The sip_core.connect task has been cancelled.")
            raise

    def on_message(self, filters: Optional[SipFilter] = None):
        def decorator(func):
            @wraps(func)
            async def wrapper(msg):
                if filters is None:
                    return await func(msg)
                else:
                    if self.evaluate(filters, msg):
                        return await func(msg)

            self.on_message_callbacks.append(wrapper)
            return func

        return decorator

    def evaluate(self, sip_filter, msg):
        # Get conditions list
        conditions = sip_filter.conditions
        if conditions and isinstance(conditions, list):
            if len(conditions) == 1:
                return conditions[0](msg)

            operator = conditions[1]
            if operator == "and":
                return self.evaluate(conditions[0], msg) and self.evaluate(
                    conditions[2], msg
                )

            if operator == "or":
                return self.evaluate(conditions[0], msg) or self.evaluate(
                    conditions[2], msg
                )

        elif not conditions:
            return sip_filter(msg)

        return False

    async def send_to_callbacks(self, data):
        for callback in self.on_message_callbacks:
            data_formatted = SipMessage(data)
            # with ThreadPoolExecutor() as executor:
            #     loop = asyncio.get_event_loop()
            #     await loop.run_in_executor(executor, data_formatted.parse)

            data_formatted.parse()

            await callback(data_formatted)

    async def send(self, msg):
        if self.connection_type == ConnectionType.UDP:
            if not self.udp_writer:
                logger.log(logging.CRITICAL, "There is no UdpWriter, cant write!")
                return
            await self.send_to_callbacks(msg)
            self.udp_writer.write(msg.encode())

        else:
            if not self.writer:
                logger.log(logging.CRITICAL, "There is no StreamWriter, can't write!")
                return
            await self.send_to_callbacks(msg)
            self.writer.write(msg.encode())
            await self.writer.drain()

    async def receive(self):
        while True:
            if not self.is_running.is_set():
                break

            if self.connection_type == ConnectionType("UDP"):
                if not self.udp_reader:
                    logger.log(logging.CRITICAL, "There is no UdpReader, can't read!")
                    return
                try:
                    data = await asyncio.wait_for(self.udp_reader.read(4096), 0.5)
                except asyncio.TimeoutError:
                    await asyncio.sleep(0.01)
                    continue  # this is neccesary to avoid blocking of checking
                    # whether app is runing or not
            else:
                if not self.reader:
                    logger.log(
                        logging.CRITICAL, "There is no StreamReader, can't read!"
                    )
                    return
                try:
                    data = await asyncio.wait_for(self.reader.read(4096), 0.5)
                except asyncio.TimeoutError:
                    await asyncio.sleep(0.01)
                    continue  # very important!!

            sip_messages = await asyncio.to_thread(self.extract_sip_messages, data)

            for sip_message_data in sip_messages:
                await self.send_to_callbacks(sip_message_data.decode())
            await asyncio.sleep(0.1)

    def extract_sip_messages(self, data: bytes) -> List[bytes]:
        messages = []
        start = 0

        while start < len(data):
            end_of_headers = data.find(b"\r\n\r\n", start)

            if end_of_headers == -1:
                break

            headers = data[start:end_of_headers].decode()
            content_length = [
                int(line.split(":")[1].strip())
                for line in headers.split("\r\n")
                if line.startswith("Content-Length:")
            ]

            total_length = (
                end_of_headers + 4 + content_length[0]
            )  # 4 for the "\r\n\r\n"
            if total_length > len(data):
                break

            message = data[start:total_length]
            messages.append(message)

            start = total_length

        return messages

    async def close_connections(self):
        # Close connections
        try:
            if self.connection_type == ConnectionType.UDP:
                if not self.udp_writer:
                    return
                if not self.udp_writer.protocol.transport:
                    return
                if self.udp_writer.protocol.transport.is_closing():
                    return
                self.udp_writer.protocol.transport.close()

            else:
                if self.writer and not self.writer.is_closing():
                    self.writer.close()
                    await self.writer.wait_closed()
        except Exception as e:
            logger.log(logging.ERROR, f"Error closing connections: {e}", exc_info=True)

        logger.log(logging.DEBUG, "Successfully closed connections")


class Checksum:
    def __init__(self, checksum: str, timestamp: str) -> None:
        self.checksum = checksum
        self.timestamp = timestamp


class Counter:
    def __init__(self, start: int = 1):
        self.x = start

    def current(self) -> int:
        return self.x

    def __iter__(self):
        return self

    def __next__(self):
        self.x += 1
        return self.x


class SipDialogue:
    def __init__(self, call_id, local_tag, remote_tag) -> None:
        self.username: Optional[str] = None
        self.call_id = call_id
        self.local_tag = local_tag  # The tag of the party who initiated the dialogue
        self.remote_tag = remote_tag  # The tag of the other party
        self.transactions: List[SipTransaction] = (
            []
        )  # List to store transactions related to this dialogue
        self.cseq = Counter(random.randint(1, 2000))
        self.state = DialogState.PREDIALOG  # Start with the PREDIALOG state
        self.events = {state: asyncio.Event() for state in DialogState}
        self.AUTH_RETRY_MAX = 1
        self.auth_retry_count = 0
        self._local_session_info: Optional[SDPParser] = None
        self._remote_session_info: Optional[SDPParser] = None
        self.remote_contact_uri: Optional[str] = None

    def matches(self, call_id, local_tag, remote_tag):
        # We now check if the provided identifiers match this dialogue's identifiers
        return (
            call_id == self.call_id
            and local_tag == self.local_tag
            and remote_tag == self.remote_tag
        )

    def add_transaction(self, branch_id, method="INVITE"):
        # Create a new transaction and add it to the dialogue's transaction list
        if method != "ACK":
            cseq = next(self.cseq)
        else:
            cseq = self.cseq.current()
        transaction = SipTransaction(self.call_id, branch_id, cseq)
        self.transactions.append(transaction)
        return transaction

    def find_transaction(self, branch_id):
        # Find a transaction by its branch ID within this dialogue
        for transaction in self.transactions:
            if transaction.branch_id == branch_id:
                return transaction
        return None

    def update_state(self, message):
        # This method should be called with each message received/sent that pertains to this dialog
        self.previous_state = self.state

        is_provisional_response = (str(message.status).startswith("18")) and (
            message.method == "INVITE"
        )
        is_final_response = (message.status is SIPStatus(200)) and (
            message.method == "INVITE"
        )
        if (
            (self.state == DialogState.PREDIALOG)
            and (message.method == "INVITE")
            and message.get_header("Authorization")
        ):
            self.state = DialogState.INITIAL

        elif self.state == DialogState.INITIAL and is_provisional_response:
            self.state = DialogState.EARLY
            if message.body is not None:
                self._remote_session_info = SDPParser(message.body)

        elif (
            self.state in [DialogState.PREDIALOG, DialogState.INITIAL, DialogState.EARLY] and is_final_response
        ):
            self.state = DialogState.CONFIRMED
            if message.body is not None:
                self._remote_session_info = SDPParser(message.body)
                self.update_remote_contact(message.get_header("Contact"))
        elif message.method == "BYE" and message.status is SIPStatus.OK:
            self.state = DialogState.TERMINATED
        elif message.status == SIPStatus(487) and message.method == "INVITE":
            self.state = DialogState.TERMINATED
        # finally we set the event for the specific state
        self.events[self.state].set()

        if self.state != self.previous_state:
            logger.log(logging.DEBUG, f"Dialog state changed to -> {self.state}")

    def update_remote_contact(self, contact_header: str) -> None:
        if contact_header:
            match = re.search(r'<(.+?)>', contact_header)
            if match:
                self.remote_contact_uri = match.group(1)
                logger.debug(f"Updated remote contact URI: {self.remote_contact_uri}")

    @property
    def local_session_info(self):
        return self._local_session_info

    @property
    def remote_session_info(self):
        return self._remote_session_info


class SipTransaction:
    def __init__(self, call_id, branch_id, cseq) -> None:
        self.call_id = call_id
        self.branch_id = branch_id
        self.cseq = cseq


class SipMessage:
    def __init__(self, message: str = "") -> None:
        self.headers = {}
        self.body = None
        self.nonce = None
        self.realm = None
        self.data = message

        # Initialize properties with default values
        self._type = None
        self._cseq = None
        self._rseq = None
        self._method = None
        self._from_tag = None
        self._to_tag = None
        self._call_id = None
        self._status: Optional[SIPStatus] = None
        self._public_ip = None
        self._rport = None
        self._branch = None
        self._did = None
        self._qop = None

    @property
    def type(self):
        return self._type

    @type.setter
    def type(self, value):
        self._type = value

    @property
    def cseq(self):
        return self._cseq

    @cseq.setter
    def cseq(self, value):
        self._cseq = value

    @property
    def rseq(self):
        return self._rseq

    @rseq.setter
    def rseq(self, value):
        self._rseq = value

    @property
    def method(self):
        return self._method

    @method.setter
    def method(self, value):
        self._method = value

    @property
    def from_tag(self):
        return self._from_tag

    @from_tag.setter
    def from_tag(self, value):
        self._from_tag = value

    @property
    def to_tag(self):
        return self._to_tag

    @to_tag.setter
    def to_tag(self, value):
        self._to_tag = value

    @property
    def call_id(self):
        return self._call_id

    @call_id.setter
    def call_id(self, value):
        self._call_id = value

    @property
    def status(self):
        return self._status

    @status.setter
    def status(self, value):
        self._status = value

    @property
    def branch(self):
        return self._branch

    @branch.setter
    def branch(self, value):
        self._branch = value

    @property
    def did(self):
        return self._did

    @did.setter
    def did(self, value):
        self._did = value

    @property
    def public_ip(self):
        return self._public_ip

    @public_ip.setter
    def public_ip(self, value):
        self._public_ip = value

    @property
    def rport(self):
        return self._rport

    @rport.setter
    def rport(self, value):
        self._rport = value

    @property
    def nonce(self):
        return self._nonce

    @nonce.setter
    def nonce(self, value):
        self._nonce = value

    @property
    def realm(self):
        return self._realm

    @realm.setter
    def realm(self, value):
        self._realm = value

    @property
    def qop(self):
        return self._qop

    @qop.setter
    def qop(self, value):
        self._qop = value

    def parse(self):
        data = self.data.split("\r\n\r\n")
        self.headers_data = data[0]
        try:
            self.body_data = data[1]
        except IndexError:
            self.body_data = ""

        headers_lines = self.headers_data.split("\r\n")
        for index, line in enumerate(headers_lines):
            if index == 0:  # First line
                self.headers["type"] = line  # Set 'type' in headers

            else:
                key, value = line.split(":", 1)  # Split at first colon
                self.headers[key.strip()] = value.strip()

        if self.body_data != "":
            body_lines = self.body_data.split("\r\n")
            self.body = {}
            for line in body_lines:
                if "=" in line:
                    key, value = line.split("=", 1)
                    if key.strip() in self.body:
                        # This expression checks if the ey value already exists in the
                        # dictionary and if it does then it makes a list of the old value
                        # and the new value, also it checks if it were already a list and just
                        # appends the value t it if it was a list.
                        if not isinstance(self.body[key.strip()], list):
                            self.body[key.strip()] = [self.body[key], value]
                        else:
                            self.body[key.strip()].append(value)
                    else:
                        self.body[key.strip()] = value.strip()

        self.set_properties()

    def set_properties(self):
        """type property, should be LITERAL[Message, Response]"""
        self.type_header = self.get_header("type").split(" ")

        if self.type_header[0] in SIPCompatibleMethods:
            self.type = SIPMessageType.MESSAGE
        elif self.type_header[0] in SIPCompatibleVersions:
            self.type = SIPMessageType.RESPONSE

        """shared properties for both request/response"""
        # CSeq
        cseq = self.get_header("CSeq")
        self.cseq = int(cseq.split(" ")[0])
        self.method = cseq.split(" ")[1]

        # From tag
        from_header = self.get_header("From")
        from_tag_match = re.search(r";tag=([^;]+)", from_header)
        self.from_tag = from_tag_match.group(1) if from_tag_match else None

        # To tag
        to_header = self.get_header("To")
        to_tag_match = re.search(r";tag=([^;]+)", to_header)
        self.to_tag = to_tag_match.group(1) if to_tag_match else None

        self.call_id = self.get_header("Call-ID")

        branch_header = self.get_header("Via")
        self.branch = branch_header.split("branch=")[1].split(";")[0]

        if self.type == SIPMessageType.RESPONSE:
            try:
                self.status = SIPStatus(int(self.type_header[1]))
                via_header = self.get_header("Via")
                self.public_ip = via_header.split("received=")[1].split(";")[0]

                # RPort
                self.rport = via_header.split("rport=")[1].split(";")[0]
                auth_header = self.get_header("WWW-Authenticate")
                if auth_header:
                    self.nonce = auth_header.split('nonce="')[1].split('"')[0]
                    self.realm = auth_header.split('realm="')[1].split('"')[0]
                    self.qop = auth_header.split("qop=")[1].split('"')[1]
                # dialog_id
                contact_header = self.get_header("Contact")
                if contact_header:
                    try:
                        self.did = contact_header.split("did=")[1].split(">")[0]
                    except IndexError:
                        pass
                # RSeq
                rseq_header = self.get_header("RSeq")
                if rseq_header:
                    self.rseq = rseq_header
            except IndexError:
                pass

            except ValueError:
                pass

    def is_from_client(self, uac_username):
        from_header = self.get_header("From")
        return str(uac_username) in from_header

    def get_header(self, key) -> str:
        return self.headers.get(key)

    def get_headers(self):
        return self.headers

    def get_body(self, key):
        return self.body.get(key)

    @classmethod
    def generate_sdp(cls, ip, port, ssrc, supported_codecs):
        cname = f"host_{random.randint(100, 999)}"

        sdp = "v=0\r\n"
        sdp += f"o=- {random.randint(100000000, 999999999)} {random.randint(100000000, 999999999)} IN IP4 {ip}\r\n"
        sdp += "s=PySIP Call\r\n"
        sdp += "b=AS:84\r\n"
        sdp += "t=0 0\r\n"
        sdp += f"m=audio {port} RTP/AVP {' '.join([str(int(i)) for i in supported_codecs])}\r\n"
        sdp += f"c=IN IP4 {ip}\r\n"
        sdp += "b=TIAS:64000\r\n"
        sdp += "a=X-nat:1\r\n"
        sdp += f"a=rtcp:{port + 1} IN IP4 {ip}\r\n"
        sdp += "a=sendrecv\r\n"
        sdp += cls.get_rtpmap_lines()
        sdp += cls.get_telephone_event_lines()
        sdp += f"a=ssrc:{ssrc} cname:{cname}\r\n"

        return sdp

    @classmethod
    def sdp_to_dict(cls, sdp):
        body_lines = sdp.split("\r\n")
        body = {}
        for line in body_lines:
            if "=" in line:
                key, value = line.split("=", 1)
                if key.strip() in body:
                    if not isinstance(body[key.strip()], list):
                        body[key.strip()] = [body[key], value]
                    else:
                        body[key.strip()].append(value)
                else:
                    body[key.strip()] = value.strip()

        return body

    @classmethod
    def dict_to_sdp(cls, sdp_dict):
        sdp_lines = []
        for key, value in sdp_dict.items():
            if isinstance(value, list):
                for v in value:
                    sdp_lines.append(f"{key}={v}")
            else:
                sdp_lines.append(f"{key}={value}")
        return "\r\n".join(sdp_lines) + "\r\n"

    @staticmethod
    def get_rtpmap_lines():
        lines = []
        lines.append("a=rtpmap:0 PCMU/8000\r\n")
        lines.append("a=rtpmap:8 PCMA/8000\r\n")
        return "".join(lines)

    @staticmethod
    def get_telephone_event_lines():
        lines = []
        lines.append("a=rtpmap:121 telephone-event/8000\r\n")
        lines.append("a=fmtp:121 0-16\r\n")
        return "".join(lines)

    @classmethod
    def parse_sdp(cls, sdp):
        parser = SDPParser(sdp)

        return parser


class SDPParser:
    def __init__(self, sdp):
        self.sdp = sdp
        self.ip_address = None
        self.media_type = None
        self.transport = None
        self.port = None
        self.rtcp_port = None
        self.ptime = None
        self.rtpmap = {}
        self.direction = None
        self.ssrc = None
        self.sdp = None

        self.parse_sdp(sdp)

    def parse_sdp(self, sdp):
        self.sdp = sdp
        self.ip_address = sdp["c"].split(" ")[2]
        m = sdp["m"].split(" ")
        self.media_type = m[0]
        self.transport = m[2]
        self.port = int(m[1])

        for attr in sdp["a"]:
            if "rtcp" in attr:
                self.rtcp_port = int(attr.split(":")[1].split(" ")[0])
            elif "ptime" in attr:
                self.ptime = int(attr.split(":")[1])
            elif "rtpmap" in attr:
                try:
                    rtpmap_val = attr.split(" ")
                    payload_type = int(rtpmap_val[0].split(":")[1])
                    codec = CodecInfo(payload_type)
                    self.rtpmap[payload_type] = codec

                except ValueError:
                    continue

            elif "sendrecv" in attr:
                self.direction = attr
            elif "ssrc" in attr:
                self.ssrc = int(attr.split(" ")[0].split(":")[1])

    def __str__(self):
        if isinstance(self.sdp, str):
            return self.sdp
        else:
            return SipMessage.dict_to_sdp(self.sdp)

    def __repr__(self):
        return str(self)
