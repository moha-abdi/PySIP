import asyncio
from dataclasses import dataclass
from enum import Enum
import logging
import queue
import random
import socket
from struct import unpack, unpack_from
import time
import threading
import numpy as np
from typing import Callable, Dict, List, Optional, Union

from .amd.amd import AnswringMachineDetector
from .exceptions import NoSupportedCodecsFound
from .jitter_buffer import JitterBuffer
from .sip_core import DTMFMode
from .audio_stream import AudioStream
from .utils.logger import logger
from .utils.inband_dtmf import dtmf_decode
from .codecs import get_encoder, get_decoder, CODECS
from .codecs.codec_info import CodecInfo


MAX_WAIT_FOR_STREAM = 40  # seconds
RTP_HEADER_LENGTH = 12
RTP_PORT_RANGE = range(10_000, 20_000)
SEND_SILENCE = True # send silence frames when no stream
USE_AMD_APP = True
DTMF_MODE = DTMFMode.AUTO


def decoder_worker(input_data, output_qs, loop):
    codec, encoded_frame = input_data
    if not encoded_frame:
        for output_q in output_qs.values():
            asyncio.run_coroutine_threadsafe(output_q.put(None), loop)
        return

    decoder = get_decoder(codec)
    if not decoder:
        logger.log(logging.WARNING, f"No decoder found for codec: {codec}")
        return

    decoded_frame = decoder.decode(encoded_frame.data)
    for output_q in output_qs.values():
        asyncio.run_coroutine_threadsafe(output_q.put(decoded_frame), loop)


@dataclass 
class DTMFBuffer:
    """for accumulating data for INBAND dtmf detection"""
    duration: int | float = 0.5
    buffer = np.array([], np.int16)
    size: int = 0
    rate: int = 8000

    def __post_init__(self):
        self.size = int(self.duration * self.rate)


def dtmf_detector_worker(input_buffer, _callbacks, loop):
    dtmf_codes = dtmf_decode(input_buffer.buffer, input_buffer.rate)

    for cb in _callbacks:
        for code in dtmf_codes:
            asyncio.run_coroutine_threadsafe(cb(code), loop)
            pass
    # finally reset buffer
    for code in dtmf_codes:
        logger.log(logging.DEBUG, "Detected INBAND DTMF key: %s", code)
    input_buffer.buffer = np.array([], np.int16)


class RTPProtocol(Enum):
    UDP = "udp"
    AVP = "RTP/AVP"
    SAVP = "RTP/SAVP"


class TransmitType(Enum):
    RECVONLY = "recvonly"
    SENDRECV = "sendrecv"
    SENDONLY = "sendonly"
    INACTIVE = "inactive"

    def __str__(self):
        return self.value


class RTPClient:
    def __init__(
        self, offered_codecs, src_ip, src_port, dst_ip, dst_port, transmit_type, ssrc,
        callbacks: Optional[Dict[str, List[Callable]]] = None
    ):
        self.offered_codecs = offered_codecs
        self.src_ip = src_ip
        self.src_port = src_port
        self.dst_ip = dst_ip
        self.dst_port = dst_port
        self.transmit_type = transmit_type
        self.selected_codec = self.select_audio_codecs(offered_codecs)
        self.udp_reader, self.udp_writer = None, None
        self.send_lock = asyncio.Lock()
        self.is_running = asyncio.Event()
        self._input_queue: asyncio.Queue = asyncio.Queue()
        self._output_queues: Dict[str, asyncio.Queue | queue.Queue] = {'audio_record': asyncio.Queue()}
        self._audio_stream: Optional[AudioStream] = None
        self.__encoder = get_encoder(self.selected_codec)
        self.__decoder = get_decoder(self.selected_codec)
        self.ssrc = ssrc
        self.__timestamp = random.randint(2000, 8000)
        self.__sequence_number = random.randint(200, 800)
        self.__jitter_buffer = JitterBuffer(16, 4)
        self.__callbacks = callbacks
        self.__send_thread = None
        self.__recv_thread = None
        self.__amd_thread = None
        self.__dtmf_thread = None
        self.DTMF_MODE = DTMF_MODE
        self.__all_threads: List[threading.Thread] = []

    async def _start(self):
        if self.DTMF_MODE is DTMFMode.AUTO:
            rfc_2833_supported = self.is_rfc_2833_supported(self.offered_codecs)
            if rfc_2833_supported:
                self.DTMF_MODE = DTMFMode.RFC_2833
            else:
                self.DTMF_MODE = DTMFMode.INBAND
            logger.log(logging.INFO, "Using DTMF Mode -> %s", self.DTMF_MODE)

        self.is_running.set()
        logger.log(
            logging.DEBUG,
            f"Establishing RTP Connection: "
            f"LOCAL: {self.src_ip}:{self.src_port} -- "
            f"SERVER: {self.dst_ip}:{self.dst_port}"
        )
        self.__rtp_socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.__rtp_socket.bind((self.src_ip, self.src_port))
        self.__rtp_socket.setblocking(False)
        self.__rtp_socket_lock = threading.Lock()

        # Start send thread 
        loop = asyncio.get_event_loop()
        self.__send_thread = threading.Thread(
            target=self.send,
            name='Send Audio Thread',
            args=(
                loop,
            ),
        )
        self.__all_threads.append(self.__send_thread)
        self.__send_thread.start()
        __send_thread_id = self.__send_thread.ident
        self.__send_thread.setName(f"Send Audio Thread - ({__send_thread_id})")

        # Start recv thread
        self.__recv_thread = threading.Thread(
            target=self.receive_sync,
            name='Receive Audio Thread',
            args=(
                loop,
            ),
        )
        self.__all_threads.append(self.__recv_thread)
        self.__recv_thread.start()
        __recv_thread_id = self.__recv_thread.ident
        self.__recv_thread.setName(f"Receive Audio Thread - ({__recv_thread_id})")

        self.__amd_detector = None
        if USE_AMD_APP: 
            self.__amd_detector = AnswringMachineDetector()
            # create an input for the amd
            self._output_queues["amd_app"] = amd_input = queue.Queue()
            amd_cb = [self.__callbacks.get("amd_app") or [] if self.__callbacks else []][0]
            self.__amd_thread = threading.Thread(
                target=self.__amd_detector.run_detector,
                name='Amd Thread',
                args=(
                    amd_input,
                    amd_cb,
                    loop,
                ),
            )
            self.__all_threads.append(self.__amd_thread)
            self.__amd_thread.start()
            __amd_thread_id = self.__amd_thread.ident
            self.__amd_thread.setName(f"AMD Thread - ({__amd_thread_id})")

        if self.DTMF_MODE is DTMFMode.INBAND:
            self.__dtmf_thread = threading.Thread(
                target=self._handle_inband,
                name='Inband DTMF Thread',
                args=(
                    loop,
                ),
            )
            self.__all_threads.append(self.__dtmf_thread)
            self.__dtmf_thread.start()
            __dtmf_thread_id = self.__dtmf_thread.ident
            self.__dtmf_thread.setName(f"Inband DTMF Thread - ({__dtmf_thread_id})")

    async def _stop(self): 
        self.is_running.clear()
        self.__rtp_socket.close() 

        logger.log(logging.DEBUG, "Rtp Handler Succesfully stopped.")
        if previos_stream := self.get_audio_stream():
            previos_stream.stream_done()
            logger.log(logging.DEBUG, "Stream ID: %s Set to Done.", previos_stream.stream_id)

        # Now put None in to the q to tell stream ended
        for output_q in self._output_queues.values():
            if isinstance(output_q, asyncio.Queue):
                await output_q.put(None)

            else:
                await asyncio.to_thread(output_q.put, None)

        # finally wait for threads to close
        logger.log(logging.DEBUG, "Closing all threads, TOTAL: %d", len(self.__all_threads))
        for t in self.__all_threads:
            await asyncio.to_thread(t.join)

    async def _wait_stopped(self):
        while True:
            if not self.is_running.is_set():
                break

            await asyncio.sleep(0.1)

    def select_audio_codecs(self, offered_codecs) -> CodecInfo:
        for codec in offered_codecs.values():
            if codec in CODECS:
                return codec

        raise NoSupportedCodecsFound

    def generate_silence_frames(self, sample_width = 2, nframes = 160):
        # Generate silence sound data or mimic sound data
        return b"\x00" * (sample_width * nframes)

    def is_rfc_2833_supported(self, offered_codecs):
        for codec in offered_codecs.values():
            if codec == CodecInfo.EVENT:
                return True

        return False

    async def _handle_rfc_2833(self, packet):
        dtmf_mapping = [
        "0", "1", "2", "3", "4", "5", "6", "7", "8", "9", "*", "#", "A", "B", "C", "D"
        ]
        payload = packet.payload
        event = dtmf_mapping[payload[0]]

        if not packet.marker:
            return

        if not self.DTMF_MODE == DTMFMode.RFC_2833:
            logger.log(logging.DEBUG, "RFC_2833 DRMF key received but ignored")
            return

        # check for registered callbacks
        if not self.__callbacks:
            logger.log(logging.DEBUG, "No callbacks passed to RtpHandler.")
            return
        if not (callbacks := self.__callbacks.get('dtmf_callback')):
            return
        # notify the callbacks
        for cb in callbacks:
            await cb(event)

    def _handle_inband(self, loop):
        # check for registered callbacks
        if not self.__callbacks:
            logger.log(logging.DEBUG, "No callbacks passed to RtpHandler.")
            return
        if not (callbacks := self.__callbacks.get('dtmf_callback')):
            return
        self._output_queues['inband_dtmf'] = dtmf_q = queue.Queue()
        _buffer = DTMFBuffer()

        while True:
            if not self.is_running.is_set():
                break

            data = dtmf_q.get() 
            if data is None:
                break

            data_array = np.frombuffer(data, np.int16)
            _buffer.buffer = np.concatenate((_buffer.buffer, data_array))

            if not (len(_buffer.buffer) >= _buffer.size):
                time.sleep(0.01)
                continue   

            dtmf_detector_worker(_buffer, callbacks, loop)
            time.sleep(0.01)

    def send(self, loop: asyncio.AbstractEventLoop):
        while True:
            if self.__rtp_socket is None or self.__rtp_socket.fileno() < 0:
                break
            start_processing = time.monotonic_ns()

            audio_stream = self.get_audio_stream()
            if not self.is_running.is_set():
                break

            if not audio_stream and not SEND_SILENCE:
                time.sleep(0.02)
                continue

            try:
                if audio_stream is None:
                    payload = self.generate_silence_frames()
                else:
                    payload = audio_stream.input_q.get_nowait()
            except queue.Empty:
                time.sleep(0.02)
                continue

            # if all frames are sent then continue
            if not payload:
                if audio_stream is None:
                    time.sleep(0.02)
                    continue
                logger.log(
                    logging.DEBUG,
                    f"Sent all frames from source with id: {audio_stream.stream_id}",
                )
                try:
                    loop.call_soon_threadsafe(audio_stream.stream_done)
                    time.sleep(0.02)
                    continue
                except RuntimeError:
                    break
            
            encoded_payload = self.__encoder.encode(payload)
            packet = RtpPacket(
                payload_type=self.selected_codec,
                payload=encoded_payload,
                sequence_number=self.__sequence_number,
                timestamp=self.__timestamp,
                ssrc=self.ssrc,
            ).serialize()
            try:
                self.__rtp_socket.setblocking(True)
                self.__rtp_socket.sendto(packet, (self.dst_ip, self.dst_port))
                self.__rtp_socket.setblocking(False)
            except OSError:
                logger.log(logging.ERROR, "Failed to send RTP Packet", exc_info=True)

            delay = (1 / self.selected_codec.rate) * 160
            processing_time = (time.monotonic_ns() - start_processing) / 1e9
            sleep_time = delay - processing_time
            sleep_time = max(0, sleep_time)
            self.__sequence_number = (self.__sequence_number + 1) % 65535  # Wrap around at 2^16 - 1
            self.__timestamp = (self.__timestamp + len(encoded_payload)) % 4294967295  # Wrap around at 2^32 -1

            time.sleep(sleep_time)
        
        logger.log(logging.DEBUG, "Sender thread has been successfully closed") 

    def receive_sync(self, loop):
        while True:
            if not self.is_running.is_set():
                break
            if self.__rtp_socket is None or self.__rtp_socket.fileno() < 0:
                    break

            try: 
                data = self.__rtp_socket.recv(4096)
                if data is None:
                    break

                packet = RtpPacket.parse(data)
                if packet.payload_type == CodecInfo.EVENT:
                    # handle rfc 2833 
                    if self.DTMF_MODE is DTMFMode.RFC_2833:
                        try:
                            asyncio.run_coroutine_threadsafe(
                                self._handle_rfc_2833(packet), loop
                            )
                        except RuntimeError:
                            break
                    time.sleep(0.01)
                    continue

                if packet.payload_type not in CODECS:
                    logger.log(logging.WARNING, f"Unsupported codecs received, {packet.payload_type}")
                    time.sleep(0.01)
                    continue

                encoded_frame = self.__jitter_buffer.add(packet)
                # if we have enough encoded buffer then decode
                if encoded_frame:
                    if self.__amd_detector and not self.__amd_detector.amd_started.is_set():
                        self.__amd_detector.amd_started.set()
                    decoded_frame = self.__decoder.decode(encoded_frame.data)
                    for output_q in self._output_queues.values():
                        if isinstance(output_q, asyncio.Queue):
                            # asyncio.run_coroutine_threadsafe(output_q.put(decoded_frame), loop)
                            try:
                                loop.call_soon_threadsafe(output_q.put_nowait, decoded_frame)
                            except RuntimeError:
                                break
                        elif isinstance(output_q, queue.Queue):
                            output_q.put(decoded_frame)

                time.sleep(0.01)

            except BlockingIOError:
                time.sleep(0.01)
            except OSError:
                time.sleep(0.01)
                pass

        logger.log(logging.DEBUG, "Receiver socket successfully closed") 

    async def frame_monitor(self):
        # first add stream queue to the output _output_queues
        self._output_queues['frame_monitor'] = stream_q = asyncio.Queue()
        while True:
            if not self.is_running.is_set():
                break
            if not self.__callbacks:
                logger.log(logging.DEBUG, "No callbacks passed to RtpHandler.")
                break
            try:
                frame = await stream_q.get()
                if frame is None:
                    break
                if not (callbacks := self.__callbacks.get('frame_monitor')):
                    break
                # check for registered callbacks
                for cb in callbacks:
                    await cb(frame)
                await asyncio.sleep(0.1)

            except asyncio.QueueEmpty:
                await asyncio.sleep(0.1)
                continue

    def get_audio_stream(self):
        return self._audio_stream

    def set_audio_stream(self, stream: Union[AudioStream, None]):
        # if there is previous stream mark it as done
        if audio_stream := self.get_audio_stream():
            audio_stream.stream_done()
        self._audio_stream = stream

        if stream:
            logger.log(logging.DEBUG, f"Set new stream with id: {stream.stream_id}")
        else:
            logger.log(logging.DEBUG, "Set the stream to No stream")

    @property
    def _rtp_task(self) -> asyncio.Task:
        return self.__rtp_task

    @_rtp_task.setter
    def _rtp_task(self, value: asyncio.Task):
        self.__rtp_task = value


class RtpPacket:
    def __init__(
        self,
        payload_type: CodecInfo = CodecInfo.PCMA,
        marker: int = 0,
        sequence_number: int = 0,
        timestamp: int = 0,
        ssrc: int = 0,
        payload: bytes = b"",
    ):
        self.payload_type = payload_type
        self.sequence_number = sequence_number
        self.timestamp = timestamp
        self.marker = marker
        self.ssrc = ssrc
        self.csrc: List[int] = []
        self.padding_size = 0
        self.payload = payload

    def serialize(self) -> bytes:
        packet = b"\x80"
        packet += chr(int(self.payload_type)).encode("utf8")
        packet += self.get_header()
        packet += self.payload
        return packet

    def get_header(self):
        seq = self.sequence_number.to_bytes(2, byteorder="big")
        ts = self.timestamp.to_bytes(4, byteorder="big")

        ssrc = self.ssrc.to_bytes(4, byteorder="big")
        header = seq + ts + ssrc
 
        return header

    @classmethod
    def parse(cls, data: bytes):
        if len(data) < RTP_HEADER_LENGTH:
            raise ValueError(
                f"RTP packet length is less than {RTP_HEADER_LENGTH} bytes"
            )

        v_p_x_cc, m_pt, sequence_number, timestamp, ssrc = unpack("!BBHLL", data[0:12])
        version = v_p_x_cc >> 6
        padding = (v_p_x_cc >> 5) & 1
        extension = (v_p_x_cc >> 4) & 1
        cc = v_p_x_cc & 0x0F
        if version != 2:
            raise ValueError("RTP packet has invalid version")
        if len(data) < RTP_HEADER_LENGTH + 4 * cc:
            raise ValueError("RTP packet has truncated CSRC")

        try:
            payload_type = CodecInfo((m_pt & 0x7F))
        except ValueError:
            payload_type = CodecInfo.UNKNOWN

        packet = cls(
            marker=(m_pt >> 7),
            payload_type=payload_type,
            sequence_number=sequence_number,
            timestamp=timestamp,
            ssrc=ssrc,
        )

        pos = RTP_HEADER_LENGTH
        for _ in range(0, cc):
            packet.csrc.append(unpack_from("!L", data, pos)[0])
            pos += 4

        if extension:
            # not neccesary currently so just pass
            pass

        if padding:
            padding_len = data[-1]
            if not padding_len or padding_len > len(data) - pos:
                raise ValueError("RTP packet padding length is invalid")
            packet.padding_size = padding_len
            packet.payload = data[pos:-padding_len]
        else:
            packet.payload = data[pos:]

        return packet
