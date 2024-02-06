import asyncio
from functools import wraps
import os
import re
import socket
import ssl
import time
import uuid
import hashlib
import hmac
import base64
import configparser
from typing import Callable, Dict, List, Literal
import warnings
import traceback

import requests
from .filters import SipFilter, SipMessage, SIPMessageType, SIPCompatibleMethods, SIPStatus, ConnectionType, CallState
from . import _print_debug_info
from .udp_handler import open_udp_connection

__all__ = [
    'Client',
    'Checksum',
    'Counter',
    'SipFilter',
    'SipMessage',
    'SIPMessageType',
    'SIPCompatibleMethods',
    'SIPStatus'
]


class NoPasswordFound(Exception):
    def __init__(self, *args: object) -> None:
        super().__init__(*args)


class Checksum:
    def __init__(self, checksum: str, timestamp: str) -> None:
        self.checksum = checksum
        self.timestamp = timestamp

class Counter:
    def __init__(self, start: int = 1):
        self.x = start

    def count(self) -> int:
        x = self.x
        self.x += 1
        return x

    def next(self) -> int:
        return self.count()

    def current(self) -> int:
        return self.x


class Client:

    def __init__(
        self, username, server, callee, connection_type: str,
        from_tag=None, password=None, device_id=None, token=None
    ):
        self.username = username
        self.from_tag = from_tag if from_tag else username
        self.server = server.split(":")[0]
        self.port = server.split(":")[1]
        self.callee = callee

        if password:
            self.password = password
        else:
            raise NoPasswordFound("No password was provided please provide password to use for Digest auth.")
            self.device_id = device_id
            self.password = self.generate_password()

        self.is_running = False
        self.call_state: Callable[[], CallState] = None
        self.set_call_state: Callable[[CallState], None] = None
        self.CTS = 'TLS' if 'TLS' in connection_type else connection_type
        self.connection_type = ConnectionType(connection_type)
        self.token = token
        self.reader, self.writer = None, None
        self.call_id_counter = 0
        self.tags = []
        self.urn_uuid = self.generate_urn_uuid()
        self.call_id = self.gen_call_id()
        self.on_message_callbacks = [self.message_handler]
        self.my_private_ip = self.get_local_ip()
        self.my_puplic_ip = self.get_public_ip()
        self.register_counter = Counter(29809)
        self.rseq_counter = Counter()
        self.urn_UUID = self.gen_urn_uuid()
        self.invite_details: SipMessage = None
        self.dialog_id = None
        self.on_call_tags: Dict[Literal["From", "To", "CSeq", "RSeq", "branch"], str] = \
                            {"From": None, "To": None, "CSeq": None, "RSeq": None, "branch": None}
        self.last_invite_msg = None
        self.last_register_msg = None
        self.pysip_tasks = []

    async def main(self):
        register_task = None
        receive_task = None
        try:
            await self.connect()
            register_task = asyncio.create_task(self.periodic_register(60), name='pysip_8')
            await asyncio.sleep(0.02)
            receive_task = asyncio.create_task(self.receive(), name='pysip_9')
            await self.invite()

            try:
                await receive_task
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

    async def periodic_register(self, delay: float):
        while self.is_running:
            await self.register()
            await asyncio.sleep(delay)

    def generate_password(self, method=None, username=None):
        if method:
            timestamp = str(int(time.time() * 1000))
            salt = self.gather_salts("salt_2").encode()
            user = self.from_tag if not username else username
            message = (method + user + "@" + self.server + timestamp).encode()

            message_hash = hmac.new(salt, message, hashlib.sha512).digest()
            hashb64 = base64.b64encode(message_hash).decode()

            return Checksum(hashb64, timestamp)
        else:
            salt = self.gather_salts("salt_1").encode()
            message = (self.device_id + self.username).encode()

            message_hash = hmac.new(salt, message, hashlib.sha512).digest()
            hashb64 = base64.b64encode(message_hash).decode()

            return hashb64

    def get_public_ip(self) -> str | None:
        try:
            external_ip = requests.get('https://api64.ipify.org?format=json', timeout=8).json()['ip']
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
            ip = "Error: " + str(e)
            _print_debug_info(ip)
        return ip

    def gather_salts(self, target_salt: str) -> str:
        config = configparser.ConfigParser()
        file_path = os.path.join(os.getcwd(), 'secrets.ini')

        if not os.path.exists(file_path):
            raise Exception('No secrets.ini file found please create it and add required keys.')

        config.read(file_path)
        salt = config.get("credentials", target_salt)

        return salt

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

    def generate_response(self, method, nonce, realm, uri):
        A1_string = (self.username + ":" + realm + ":" + self.password)
        A1_hash = hashlib.md5(A1_string.encode()).hexdigest()

        A2_string = (method + ":" + uri).encode()
        A2_hash = hashlib.md5(A2_string).hexdigest()

        response_string = (A1_hash + ":" + nonce + ":" + A2_hash).encode()
        response_hash = hashlib.md5(response_string).hexdigest()

        return response_hash

    async def connect(self):
        try:
            if self.connection_type == ConnectionType.TCP:
                self.is_running = True
                self.reader, self.writer = await asyncio.open_connection(
                    self.server,
                    self.port,
                )

            elif self.connection_type == ConnectionType.UDP:
                self.is_running = True

                self.reader, self.writer = await open_udp_connection(
                    self.server,
                    self.port
                )

            elif self.connection_type == ConnectionType.TLS:
                self.is_running = True
                ssl_context = ssl.create_default_context(ssl.Purpose.CLIENT_AUTH)
                self.reader, self.writer = await asyncio.open_connection(
                    self.server,
                    self.port,
                    ssl=ssl_context
                )

            elif self.connection_type == ConnectionType.TLSv1:
                self.is_running = True
                ssl_context = ssl.SSLContext(ssl.PROTOCOL_TLSv1)
                ssl_context.set_ciphers("AES128-SHA")
                ssl_context.keylog_filename = 'premaster.txt'
                self.reader, self.writer = await asyncio.open_connection(
                    self.server,
                    self.port,
                    ssl=ssl_context
                )

        except (OSError, ssl.SSLError) as e:
            print(f"Error during connection: {e}")
            # Handle the error as needed
        except Exception as e:
            print(f"Unexpected error: {e}")
        except asyncio.CancelledError:
            print("Cancelled task")

    def build_register_message(self, auth=False, msg=None, data=None):

        if auth:
            received_message: SipMessage = data
            nonce = received_message.nonce
            realm = received_message.realm
            ip = received_message.public_ip
            port = received_message.rport

            if not self.my_puplic_ip:
                self.my_puplic_ip = ip

            new_via = f"Via: SIP/2.0/{self.CTS} {ip}:{port};rport;branch={str(uuid.uuid4()).upper()};alias\r\n"
            msg = re.sub(r"Via:.*[\r\n]", new_via, msg, flags=re.M)

            new_contact = (f"Contact: <sip:{self.username}@{ip}:{port};transport={self.CTS};ob>;" +
            f'reg-id=1;+sip.instance="<urn:uuid:{self.urn_UUID}>"\r\n')
            msg = re.sub(r"Contact:.*[\r\n]", new_contact, msg, flags=re.M)

            msg = msg.replace(
                f"Content-Length: 0\r\n\r\n", ''
            )

            msg = re.sub(r"CSeq: \d+", f"CSeq: {self.register_counter.next()}", msg)

            uri = f'sip:{self.server}:{self.port};transport={self.CTS}'
            msg += (f'Authorization: Digest username="{self.username}",' +
                    f'realm="{realm}", nonce="{nonce}", uri="{uri}",'
                    f'response="{self.generate_response("REGISTER", nonce, realm, uri)}",' +
                    f'algorithm="MD5"\r\n')
            msg += "Content-Length: 0\r\n\r\n"

        else:
            ip = self.my_private_ip
            port = self.port

            branch_id = uuid.uuid4()
            call_id = self.call_id
            tag = self.generate_tag()
            # generated_checksum = self.generate_password(method='REGISTER') # not required at all

            msg = (f"REGISTER sip:{self.server} SIP/2.0\r\n"
                f"Via: SIP/2.0/{self.CTS} {ip}:{port};rport;branch={str(branch_id).upper()};alias\r\n"
                f"Route: <sip:{self.server}:{port};transport={self.CTS};lr>\r\n"
                f"Max-Forwards: 70\r\n"
                f"From: <sip:{self.from_tag}@{self.server}>;tag={tag}\r\n"
                f"To: <sip:{self.username}@{self.server}>\r\n"
                f"Call-ID: {call_id}\r\n"
                f"CSeq: {self.register_counter.next()} REGISTER\r\n"
                # f"Client-Checksum: {generated_checksum.checksum}\r\n"
                # f"Client-Timestamp: {generated_checksum.timestamp}\r\n"
                f"Supported: outbound, path\r\n"
                f"Contact: <sip:{self.username}@{ip}:{port};transport={self.CTS};ob>;" +
                f'reg-id=1;+sip.instance="<urn:uuid:{self.urn_UUID}>"\r\n'
                f"Expires: 60\r\n"
                f"Allow: {', '.join(SIPCompatibleMethods)}\r\n"
                f"Content-Length: 0\r\n\r\n")


        return msg

    def build_invite_message(self, auth=False, msg=None, data=None):
        _, port = self.writer.get_extra_info('sockname')
        ip = self.my_puplic_ip

        if auth:
            received_message: SipMessage = data
            nonce = received_message.nonce
            realm = received_message.realm
            ip = received_message.public_ip
            port = received_message.rport

            new_cseq = f"CSeq: {self.register_counter.next()} INVITE\r\n"
            msg = re.sub(r"CSeq:.*[\r\n]", new_cseq, msg, flags=re.M)

            uri = f'sip:{self.callee}@{self.server}:{self.port};transport={self.CTS}'
            old_content_type = re.findall(r"Content-Type:.*[\r\n]", msg)

            new_value = ((f'Authorization: Digest username="{self.username}",' +
                    f'realm="{realm}", nonce="{nonce}", uri="{uri}",'
                    f'response="{self.generate_response("INVITE", nonce, realm, uri)}",'+
                    f'algorithm="MD5"\r\n') + old_content_type[0])

            msg = msg.replace(old_content_type[0], new_value)

            self.invite_details = SipMessage(msg)
            self.invite_details.parse()

            return msg

        else:
            tag = self.generate_tag()
            call_id = self.call_id
            generated_checksum = self.generate_password(method='INVITE') # not required for most SIPs

            msg = f"INVITE sip:{self.callee}@{self.server}:{self.port};transport={self.CTS} SIP/2.0\r\n"
            msg += f"Via: SIP/2.0/{self.CTS} {ip}:{port};rport;branch={str(uuid.uuid4()).upper()};alias\r\n"
            msg += f"Max-Forwards: 70\r\n"
            msg += f"From:sip:{self.from_tag}@{self.server};tag={tag}\r\n"
            msg += f"To: sip:{self.callee}@{self.server}\r\n"
            msg += f"Contact: <sip:{self.username}@{ip}:{port};transport={self.CTS};ob>\r\n"
            msg += f"Call-ID: {call_id}\r\n"
            msg += f"CSeq: {self.register_counter.next()} INVITE\r\n"
            msg += f"Route: <sip:{self.server}:{self.port};transport={self.CTS};lr>\r\n"
            msg += f"Allow: {', '.join(SIPCompatibleMethods)}\r\n"
            msg += f"Supported: replaces, 100rel, timer, norefersub\r\n"
            msg += f"Session-Expires: 1800\r\n"
            msg += f"Min-SE: 90\r\n"
            # msg += f"Client-Checksum: {generated_checksum.checksum}\r\n"
            # msg += 'Location:{"MNC":"01","MCC":"637"}\r\n'
            msg += f"User-Agent: PySIP-1.4.0\r\n"
            # msg += f"Client-Timestamp: {generated_checksum.timestamp}\r\n"
            msg += f"Content-Type: application/sdp\r\n"

            body = SipMessage.generate_sdp(ip)
            msg += f"Content-Length:   {len(body.encode())}\r\n\r\n"
            msg += body

            return msg

    def ack_generator(self, data):
        _, port = self.writer.get_extra_info('sockname')
        ip = self.my_puplic_ip

        data_parsed = SipMessage(data)
        data_parsed.parse()

        msg = f"ACK sip:{self.callee}@{self.server}:{self.port};transport={self.CTS} SIP/2.0\r\n"
        msg += f"Via: SIP/2.0/{self.CTS} {ip}:{port};rport;branch={str(uuid.uuid4()).upper()};alias\r\n"
        msg += f"Max-Forwards: 70\r\n"
        msg += f"From: sip:{self.from_tag}@{self.server};tag={data_parsed.from_tag}\r\n"
        msg += f"To: sip:{self.callee}@{self.server};tag={data_parsed.to_tag}\r\n"
        msg += f"Call-ID: {data_parsed.call_id}\r\n"
        msg += f"CSeq: {data_parsed.cseq} ACK\r\n"
        msg += f"Route: <sip:{self.server}:{self.port};transport={self.CTS};lr>\r\n"
        msg += f"Content-Length:  0\r\n\r\n"

        return msg

    def ack_call_answered(self):
        peer_ip, peer_port = self.writer.get_extra_info("peername")
        _, port = self.writer.get_extra_info('sockname')

        msg = f"ACK sip:{peer_ip}:{self.port};transport={self.CTS.lower()};did={self.dialog_id} SIP/2.0\r\n"
        msg += f"Via: SIP/2.0/{self.CTS} {self.my_puplic_ip}:{port};rport;branch={self.on_call_tags['branch']};alias\r\n"
        msg += f"Max-Forwards: 70\r\n"
        msg += f"From: sip:{self.from_tag}@{self.server};tag={self.invite_details.from_tag}\r\n"
        msg += f"To: sip:{self.callee}@{self.server};tag={self.on_call_tags['To']}\r\n"
        msg += f"Call-ID: {self.call_id}\r\n"
        msg += f"CSeq: {self.invite_details.cseq} ACK\r\n"
        msg += f"Content-Length:  0\r\n\r\n"

        return msg

    def cancel_generator(self):
        _, port = self.writer.get_extra_info('sockname')
        ip = self.my_puplic_ip

        msg = f"CANCEL sip:{self.callee}@{self.server}:{self.port};transport={self.CTS} SIP/2.0\r\n"
        msg += (f"Via: SIP/2.0/{self.CTS} {ip}:{port};" +
                f"rport;branch={self.invite_details.branch};alias\r\n")
        msg += f"Max-Forwards: 70\r\n"
        msg += f"From:sip:{self.from_tag}@{self.server};tag={self.invite_details.from_tag}\r\n"
        msg += f"To: sip:{self.callee}@{self.server}\r\n"
        msg += f"Call-ID: {self.invite_details.call_id}\r\n"
        msg += f"CSeq: {self.invite_details.cseq} CANCEL\r\n"
        msg += f"Route: <sip:{self.server}:{self.port};transport={self.CTS};lr>\r\n"
        msg += f"Content-Length:  0\r\n\r\n"

        return msg

    def prack_generator(self):
        peer_ip, peer_port = self.writer.get_extra_info("peername")
        _, port = self.writer.get_extra_info('sockname')

        msg = f"PRACK sip:{peer_ip}:{self.port};transport={self.CTS.lower()};did={self.dialog_id} SIP/2.0\r\n"
        msg += f"Via: SIP/2.0/{self.CTS} {self.my_puplic_ip}:{port};rport;branch={str(uuid.uuid4()).upper()};alias\r\n"
        msg += f"Max-Forwards: 70\r\n"
        msg += f"From: sip:{self.from_tag}@{self.server};tag={self.on_call_tags['From']}\r\n"
        msg += f"To: sip:{self.callee}@{self.server};tag={self.on_call_tags['To']}\r\n"
        msg += f"Call-ID: {self.call_id}\r\n"
        msg += f"CSeq: {self.register_counter.next()} PRACK\r\n"
        Rack = self.on_call_tags["RSeq"] if self.on_call_tags["RSeq"] else self.rseq_counter.next()
        msg += f"RAck:{Rack} {self.on_call_tags['CSeq']} INVITE\r\n"
        msg += f"Content-Length:0\r\n\r\n"

        return msg

    def bye_generator(self):
        peer_ip, peer_port = self.writer.get_extra_info("peername")
        _, port = self.writer.get_extra_info('sockname')

        msg = f"BYE sip:{self.callee}@{peer_ip}:{peer_port};transport={self.CTS.lower()};did={self.dialog_id} SIP/2.0\r\n"
        msg += (f"Via: SIP/2.0/{self.CTS} {self.my_puplic_ip}:{port};rport;" +
                f"branch={str(uuid.uuid4()).upper()};alias\r\n")
        msg += 'Reason: Q.850;cause=16;text="normal call clearing"'
        msg += f"Max-Forwards: 64\r\n"
        msg += f"From: sip:{self.from_tag}@{self.server};tag={self.on_call_tags['From']}\r\n"
        msg += f"To:sip:{self.callee}@{self.server};tag={self.on_call_tags['To']}\r\n"
        msg += f"Call-ID: {self.call_id}\r\n"
        msg += f"CSeq: {self.register_counter.next()} BYE\r\n"
        msg += f"Content-Length:  0\r\n\r\n"

        return msg

    def ok_generator(self, data_parsed: SipMessage):
        peer_ip, peer_port = self.writer.get_extra_info("peername")
        _, port = self.writer.get_extra_info('sockname')
        from_tag = ";tag=" + data_parsed.from_tag if data_parsed.from_tag else ""
        to_tag = ";tag=" + data_parsed.to_tag if data_parsed.to_tag else ""

        msg = f"SIP/2.0 200 OK\r\n"
        msg += (f"Via: SIP/2.0/{self.CTS} {self.my_puplic_ip}:{port};rport;" +
                f"branch={data_parsed.branch}\r\n")
        msg += f"From: <sip:{self.from_tag}@{self.server}>{from_tag}\r\n"
        msg += f"To: <sip:{self.callee}@{self.server}>{to_tag}\r\n"
        msg += f"Call-ID: {data_parsed.call_id}\r\n"
        msg += f"CSeq: {data_parsed.cseq} {data_parsed.method}\r\n"
        msg += f"Contact: <sip:{self.username}@{self.my_puplic_ip}:{port};transport={self.CTS.upper()};ob>\r\n"
        msg += f"Allow: {', '.join(SIPCompatibleMethods)}\r\n"
        msg += f"Supported: replaces, 100rel, timer\r\n"
        msg += f"Content-Length: 0\r\n\r\n"

        return msg

    def options_generator(self):
        peer_ip, peer_port = self.writer.get_extra_info("peername")
        _, port = self.writer.get_extra_info('sockname')

        msg = f"OPTIONS sip:{peer_ip}:{self.port};transport={self.CTS.lower()} SIP/2.0\r\n"
        msg += f"Via: SIP/2.0/{self.CTS} {self.my_puplic_ip}:{port};rport;branch={self.on_call_tags['branch']};alias\r\n"
        msg += f"Max-Forwards: 70\r\n"
        msg += f"From: sip:{self.from_tag}@{self.server};tag={self.invite_details.from_tag}\r\n"
        msg += f"To: sip:{self.callee}@{self.server};tag={self.on_call_tags['To']}\r\n"
        msg += f"Call-ID: {self.call_id}\r\n"
        msg += f"CSeq: {self.register_counter.next()} OPTIONS\r\n"
        msg += f"Content-Length: 0\r\n\r\n"

        return msg

    def refer_generator(self, refer_to_callee):
        _, port = self.writer.get_extra_info('sockname')
        ip = self.my_puplic_ip

        # the refer-to header - the sip uri of the person to refer to
        refer_to = f"sip:{refer_to_callee}@{self.server};transport={self.CTS}"

        # referred-by header - similar to the from header in invite
        referred_by = f"sip:{self.from_tag}@{self.server}"

        msg = f"refer sip:{self.callee}@{self.server}:{self.port};transport={self.CTS} sip/2.0\r\n"
        msg += f"via: sip/2.0/{self.CTS} {ip}:{port};rport;branch={str(uuid.uuid4()).upper()};alias\r\n"
        msg += f"max-forwards: 70\r\n"
        msg += f"from: sip:{self.from_tag}@{self.server};tag={self.generate_tag()}\r\n"
        msg += f"to: sip:{self.callee}@{self.server}\r\n"
        msg += f"call-id: {self.call_id}\r\n"
        msg += f"cseq: {self.register_counter.next()} refer\r\n"
        msg += f"refer-to: {refer_to}\r\n"
        msg += f"referred-by: {referred_by}\r\n"
        msg += f"contact: <sip:{self.username}@{ip}:{port};transport={self.CTS};ob>\r\n"
        msg += f"content-length: 0\r\n\r\n"

        return msg

    def on_message(self, filters:SipFilter=None):
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
                return self.evaluate(conditions[0], msg) and self.evaluate(conditions[2], msg)

            if operator == "or":
                return self.evaluate(conditions[0], msg) or self.evaluate(conditions[2], msg)

        elif not conditions:
            return sip_filter(msg)

        return False

    async def send_to_callbacks(self, data):
        for callback in self.on_message_callbacks:
            data_formatted = SipMessage(data)
            data_formatted.parse()
            await callback(data_formatted)

    async def send(self, msg):
        if self.connection_type == ConnectionType.UDP:
            await self.send_to_callbacks(msg)
            await self.writer.write(msg.encode())

        else:
            await self.send_to_callbacks(msg)
            self.writer.write(msg.encode())
            await self.writer.drain()

    async def receive(self):
        while self.is_running:
            data = await self.reader.read(4096)
            sip_messages = self.extract_sip_messages(data)
            # print(f"Received {len(sip_messages)} messages")

            for sip_message_data in sip_messages:
                await self.send_to_callbacks(sip_message_data.decode())

    async def ping(self):
        options_message = self.options_generator()
        await self.send(options_message)

    def extract_sip_messages(self, data: bytes) -> List[bytes]:
        messages = []
        start = 0 

        while start < len(data):
            end_of_headers = data.find(b'\r\n\r\n', start)

            if end_of_headers == -1:
                break

            headers = data[start:end_of_headers].decode()
            content_length = [int(line.split(':')[1].strip()) for line in headers.split("\r\n") if line.startswith('Content-Length:')]

            total_length = end_of_headers + 4 + content_length[0] # 4 for the "\r\n\r\n"
            if total_length > len(data):
                break

            message = data[start:total_length]
            messages.append(message)

            start = total_length

        return messages


    async def reregister(self, auth, msg, data):
        msg = self.build_register_message(auth, msg, data)

        await self.send(msg)
        return

    async def register(self):
        msg = self.build_register_message()
        self.last_register_msg = msg

        await self.send(msg)
        return


    async def reinvite(self, auth, msg, data):
        reinvite_msg = self.build_invite_message(auth, msg, data)
        await self.send(reinvite_msg)
        return

    async def invite(self):
        msg = self.build_invite_message()
        self.last_invite_msg = msg

        await self.send(msg)
        return

    async def hangup(self, rtp_session = None, callee_hanged_up = False, data_parsed = None):
        if not self.call_state() is CallState.ANSWERED:
            warnings.warn('WARNING! There is no call in-progress trying to cancel instead..')
        if self.call_state() is CallState.ENDED:
            _print_debug_info("Call is hanged up already")
            return
        self.set_call_state(CallState.ENDED)

        await self.cancel(callee_hanged_up, data_parsed)
        if rtp_session:
            rtp_session.stop()

    async def cancel(self, callee_hanged_up, data_parsed):
        if not self.invite_details:
            warnings.warn('WARNING! There is no invite request to cancel')
            self.is_running = False

            return

        if self.call_state() is CallState.ANSWERED:
            if callee_hanged_up:
                msg = self.ok_generator(data_parsed=data_parsed)
            else:
                msg = self.bye_generator()
        else:
            msg = self.cancel_generator()

        await self.send(msg)
        self.is_running = False
        _print_debug_info("Client stopped")


    async def cleanup(self):
        # Close connections
        try:
            if self.connection_type == ConnectionType.UDP:
                if self.writer and not self.writer.protocol.transport.is_closing():
                    self.writer.protocol.transport.close()
            else:
                if self.writer and not self.writer.is_closing():
                    self.writer.close()
                    await self.writer.wait_closed()
                    pass
        except Exception as e:
            print(f"Error during cleanup: {e}")
            # Cancel all tasks

        for task in self.pysip_tasks:
            if task.done() or task.cancelled():
                continue
            task.cancel()

        # Await task completion/cancellation
        await asyncio.gather(*self.pysip_tasks, return_exceptions=True)

        _print_debug_info("Cleanup completed")   

    async def message_handler(self, msg: SipMessage):
        # This is the main message handler inside the class
        # its like other handlers outside the class that can
        # be accessed with @:meth:`Client.on_message` the only
        # difference is that its handled inside the :obj:`Client`
        # and it's onlt for developer's usage. unlike other handlers
        # it has no filters for now.
        # print(msg.data)
        await asyncio.sleep(0.001)
        if msg.status == SIPStatus(401) and msg.method == "REGISTER":
            # This is the case when we have to send a retegister
            await self.reregister(True, self.last_register_msg, msg)
            _print_debug_info("REGISTERING...")

        elif msg.status == SIPStatus(401) and msg.method == "INVITE":
            # This is the case when we have to send a reinvite
            ack_message = self.ack_generator(msg.data)
            await self.send(ack_message)
            await self.reinvite(True, self.last_invite_msg, msg)
            _print_debug_info("INVITING...")

        elif msg.status == SIPStatus(200) and msg.method == "REGISTER":
            # This is when we receive the response for the register
            _print_debug_info("RE-REGISTERED...")

        elif msg.status == SIPStatus(200) and msg.method == "INVITE":
            # This is when we receive the response for the invite
            _print_debug_info("RE-INVITED...")
