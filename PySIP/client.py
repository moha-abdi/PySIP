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
from typing import Dict, Literal
import warnings

import requests
from .filters import SipFilter, SipMessage, SIPMessageType, SIPCompatibleMethods, SIPStatus, ConnectionType
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
        password=None, device_id=None, token=None
    ):
        self.username = username
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
        self.CTS = 'TLS' if 'TLS' in connection_type else connection_type
        self.connection_type = ConnectionType(connection_type)
        self.token = token
        self.reader, self.writer = None, None
        self.call_id_counter = 0
        self.tags = []
        self.urn_uuid = self.generate_urn_uuid()
        self.call_id = self.gen_call_id()
        self.on_message_callbacks = [self.message_handler]
        self.my_private_ip = socket.gethostbyname(socket.gethostname())
        self.my_puplic_ip = self.get_public_ip()
        self.register_counter = Counter(29809)
        self.rseq_counter = Counter()
        self.urn_UUID = self.gen_urn_uuid()
        self.invite_details: SipMessage = None
        self.dialog_id = None
        self.on_call_tags: Dict[Literal["From", "To", "CSeq", "RSeq"], str] = \
                            {"From": None, "To": None, "CSeq": None, "RSeq": None}

    async def main(self):
        try:
            await self.connect()
            await self.register()

        except Exception as e:
            print("Error: ", e)
            return

        finally:
            print("Main-loop completed. with no errors.")
            return

    def generate_password(self, method=None):
        if method:
            timestamp = str(int(time.time() * 1000))
            salt = self.gather_salts("salt_2").encode()
            message = (method + self.username + "@" + self.server + timestamp).encode()

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

    def generate_response(self, method, nonce, uri):
        A1_string = (self.username + ":" + self.server + ":" + self.password)
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

    def build_register_message(self, auth=False, msg=None, data=None):

        if auth:
            received_message = SipMessage(data)
            received_message.parse()
            nonce = received_message.nonce
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
                    f'realm="{self.server}", nonce="{nonce}", uri="{uri}",'
                    f'response="{self.generate_response("REGISTER", nonce, uri)}"\r\n')
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
                f"From: <sip:{self.username}@{self.server}>;tag={tag}\r\n"
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
            received_message = SipMessage(data)
            received_message.parse()
            nonce = received_message.nonce
            ip = received_message.public_ip
            port = received_message.rport

            new_cseq = f"CSeq: {self.register_counter.next()} INVITE\r\n"
            msg = re.sub(r"CSeq:.*[\r\n]", new_cseq, msg, flags=re.M)

            uri = f'sip:{self.callee}@{self.server}:{self.port};transport={self.CTS}'
            old_client_timestamp = re.findall(r"Client-Timestamp:.*[\r\n]", msg)

            new_value = (old_client_timestamp[0] +
                    (f'Authorization: Digest username="{self.username}",' +
                    f'realm="{self.server}", nonce="{nonce}", uri="{uri}",'
                    f'response="{self.generate_response("INVITE", nonce, uri)}"\r\n'))

            msg = msg.replace(old_client_timestamp[0], new_value)

            self.invite_details = SipMessage(msg)
            self.invite_details.parse()

            return msg

        else:
            tag = self.generate_tag()
            call_id = self.call_id
            # generated_checksum = self.generate_password(method='INVITE') # not required for most SIPs

            msg = f"INVITE sip:{self.callee}@{self.server}:{self.port};transport={self.CTS} SIP/2.0\r\n"
            msg += f"Via: SIP/2.0/{self.CTS} {ip}:{port};rport;branch={str(uuid.uuid4()).upper()};alias\r\n"
            msg += f"Max-Forwards: 70\r\n"
            msg += f"From:sip:{self.username}@{self.server};tag={tag}\r\n"
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
            msg += 'Location:{"MNC":"01","MCC":"637"}\r\n'
            msg += f"User-Agent: PySIP-1.2.0\r\n"
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
        msg += f"From: sip:{self.username}@{self.server};tag={data_parsed.from_tag}\r\n"
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
        msg += f"Via: SIP/2.0/{self.CTS} {self.my_puplic_ip}:{port};rport;branch={str(uuid.uuid4()).upper()};alias\r\n"
        msg += f"Max-Forwards: 70\r\n"
        msg += f"From: sip:{self.username}@{self.server};tag={self.invite_details.from_tag}\r\n"
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
        msg += f"From:sip:{self.username}@{self.server};tag={self.invite_details.from_tag}\r\n"
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
        msg += f"From: sip:{self.username}@{self.server};tag={self.on_call_tags['From']}\r\n"
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

        msg = f"BYE sip:{peer_ip}:{self.port};transport={self.CTS.lower()};did={self.dialog_id} SIP/2.0\r\n"
        msg += (f"Via: SIP/2.0/{self.CTS} {self.my_puplic_ip}:{port};rport;" +
                f"branch={str(uuid.uuid4()).upper()};alias\r\n")
        msg += f"Max-Forwards: 70\r\n"
        msg += f"From: sip:{self.username}@{self.server};tag={self.on_call_tags['From']}\r\n"
        msg += f"To:sip:{self.callee}@{self.server};tag={self.on_call_tags['To']}\r\n"
        msg += f"Call-ID: {self.call_id}\r\n"
        msg += f"CSeq: {self.register_counter.next()} BYE\r\n"
        msg += f"Content-Length:  0\r\n\r\n"

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
        await self.send_to_callbacks(msg)
        self.writer.write(msg.encode())
        await self.writer.drain()

    async def receive(self):
        while self.is_running:
            data = await self.reader.read(4000)
            await self.send_to_callbacks(data.decode())

    async def reregister(self, auth, msg, data):
        msg = self.build_register_message(auth, msg, data)

        await self.send(msg)

        while self.is_running:
            try:
                data = await asyncio.wait_for(self.reader.read(4000), timeout=5)
                await self.send_to_callbacks(data.decode())
                await self.invite()
                break
            except asyncio.TimeoutError:
                _print_debug_info("No response received, resending re-register")
                # await self.send(msg)

    async def register(self):
        msg = self.build_register_message()

        await self.send(msg)

        while self.is_running:
            try:
                data = await asyncio.wait_for(self.reader.read(4000), timeout=5)
                await self.send_to_callbacks(data.decode())
                await self.reregister(True, msg, data.decode())
                break
            except asyncio.TimeoutError:
                _print_debug_info("No response received, resending register")
                # await self.send(msg)

    async def reinvite(self, auth, msg, data):
        reinvite_msg = self.build_invite_message(auth, msg, data)
        ack_msg = self.ack_generator(data)

        await self.send(ack_msg)
        await self.send(reinvite_msg)
        while self.is_running:
            try:
                data = await asyncio.wait_for(self.reader.read(4000), timeout=5)
                await self.send_to_callbacks(data.decode())
                await asyncio.create_task(self.receive(), name='pysip_2')
                break
            except asyncio.TimeoutError:
                _print_debug_info("No response received, resending reinvite")
                # await self.send(msg)


    async def invite(self):
        msg = self.build_invite_message()

        await self.send(msg)

        while self.is_running:
            try:
                data = await asyncio.wait_for(self.reader.read(4000), timeout=4)
                data = data.decode()

                responses = data.split("\r\n\r\n")

                for response in responses:
                    if len(response) == 0:
                        continue

                    data_parsed = SipMessage(response)
                    data_parsed.parse()

                    if data_parsed.status == SIPStatus(401):
                        await self.send_to_callbacks(response)
                        await self.reinvite(True, msg, response)
                        break

            except asyncio.CancelledError:
                break

            except asyncio.TimeoutError:
                _print_debug_info("Timeout occured on invite, will try ot resend.")

    async def hangup(self, rtp_session = None):
        if not self.dialog_id:
            warnings.warn('WARNING! There is no call in-progress trying to cancel instead..')

        await self.cancel()
        if rtp_session:
            rtp_session.stop()
        await asyncio.sleep(0.2)

    async def cancel(self):
        if not self.invite_details:
            warnings.warn('WARNING! There is no invite request to cancel')
            await asyncio.sleep(0.1)
            self.is_running = False
            await asyncio.sleep(0.2)

            await self.cleanup()
            return

        if self.dialog_id:
            msg = self.bye_generator()
        else:
            msg = self.cancel_generator()

        await self.send(msg)
        await asyncio.sleep(0.1)
        self.is_running = False
        await asyncio.sleep(0.2)

        await self.cleanup()

    async def cleanup(self):

        cancel_all = False
        for task in asyncio.all_tasks():
            if task.get_name() == 'pysip_4' and task._state == 'PENDING':
                cancel_all = True
                print("Cancelling all tasks...")
                break

        if cancel_all:
            [task.cancel() for task in asyncio.all_tasks()]

        else:
            [task.cancel() for task in asyncio.all_tasks()
             if task.get_name().startswith('pysip')]

    async def message_handler(self, msg: SipMessage):
        # This is the main message handler inside the class
        # its like other handlers outside the class that can
        # be accessed with @:meth:`Client.on_message` the only
        # difference is that its handled inside the :obj:`Client`
        # and it's onlt for developer's usage. unlike other handlers
        # it has no filters for now.
        # print(msg.data)
        pass
