import asyncio
from dataclasses import dataclass
from enum import Enum
import logging
import random
from struct import unpack, unpack_from
import time
import threading
import numpy as np
from typing import Callable, Dict, List, Optional, Union
from PySIP.amd.amd import AnswringMachineDetector

from PySIP.exceptions import AudioStreamError, NoSupportedCodecsFound
from PySIP.jitter_buffer import JitterBuffer
from PySIP.sip_core import DTMFMode
from .audio_stream import AudioStream
from .udp_handler import open_udp_connection
from .utils.logger import logger
from .utils.inband_dtmf import dtmf_decode
from .codecs import get_encoder, get_decoder, CODECS
from .codecs.codec_info import CodecInfo


MAX_WAIT_FOR_STREAM = 40  # seconds
RTP_HEADER_LENGTH = 12
RTP_PORT_RANGE = range(10_000, 20_000)
SEND_SILENCE = True # send silence frames when no stream
USE_AMD_APP = True
DTMF_MODE = DTMFMode.RFC_2833


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
    duration: int = 1
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
        self._output_queues: Dict[str, asyncio.Queue] = {'audio_record': asyncio.Queue()}
        self._audio_stream: Optional[AudioStream] = None
        self.__encoder = get_encoder(self.selected_codec)
        self.__decoder = get_decoder(self.selected_codec)
        self.ssrc = ssrc
        self.__timestamp = random.randint(2000, 8000)
        self.__sequence_number = random.randint(200, 800)
        self.__jitter_buffer = JitterBuffer(16, 4)
        self.__callbacks = callbacks
        self.__send_thread = None

    async def _start(self):
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

        )

        send_task = asyncio.create_task(self.send(), name="Rtp Send Task")
        receive_task = asyncio.create_task(self.receive(), name="Rtp receive Task")
        frame_monitor_task = asyncio.create_task(self.frame_monitor(), name="Frame Monitor Task")
        _tasks = [send_task, receive_task, frame_monitor_task]

        amd_task = None
        if USE_AMD_APP: 
            self.__amd_detector = AnswringMachineDetector()
            # create an input for the amd
            self._output_queues["amd_app"] = amd_input = asyncio.Queue()
            amd_cb = [self.__callbacks.get("amd_app") if self.__callbacks else []][0]
            amd_task = asyncio.create_task(self.__amd_detector.run_detector(
                amd_input,
                amd_cb
            ), name="AMD App Task")
            _tasks.append(amd_task)

        dtmf_task = None
        if DTMF_MODE is DTMFMode.INBAND:
            dtmf_task = asyncio.create_task(self._handle_inband(), name="Inband Dtmf Task")
            _tasks.append(dtmf_task)

        try: 
            await asyncio.gather(*_tasks)
        except asyncio.CancelledError: 
            _task = asyncio.current_task()
            if _task and _task.cancelling() > 0:
                raise

        except Exception as e:
            logger.log(logging.ERROR, e, exc_info=True)

        finally:
            for _task in _tasks:
                if _task.done():
                    continue
                _task.cancel()
                try:
                    await _task
                except asyncio.CancelledError:
                    pass

    async def _stop(self):
        # close the connections
        if not self.udp_writer or not self.udp_reader:
            raise ValueError("No UdpWriter or UdpReader")

        if not self.udp_writer.protocol.transport:
            logger.log(logging.WARNING, "Couldnt stop RTP due to Udp transport")
            return
        if self.udp_writer.protocol.transport.is_closing():
            logger.log(
                logging.WARNING, "Couldnt stop RTP, transport is already closing."
            )
            return
        self.udp_writer.protocol.transport.close()
        self.is_running.clear()
        if s := self.get_audio_stream():
            s.stream_done()
        # put None to receiver to make sure it stopped
        await self.udp_reader.protocol.data_q.put(None)
        logger.log(logging.DEBUG, "Rtp Handler Succesfully stopped.")  

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

        if not DTMF_MODE == DTMFMode.RFC_2833:
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

    async def _handle_inband(self):
        self._output_queues['inband_dtmf'] = dtmf_q = asyncio.Queue()
        _buffer = DTMFBuffer()
        while True:
            if not self.is_running.is_set():
                break

            data = await dtmf_q.get() 
            if data is None:
                break

            data_array = np.frombuffer(data, np.int16)
            _buffer.buffer = np.concatenate((_buffer.buffer, data_array))

            if not (len(_buffer.buffer) >= _buffer.size):
                await asyncio.sleep(0.01)
                continue 

            # check for registered callbacks
            if not self.__callbacks:
                logger.log(logging.DEBUG, "No callbacks passed to RtpHandler.")
                return
            if not (callbacks := self.__callbacks.get('dtmf_callback')):
                return

            loop = asyncio.get_event_loop()
            loop.run_in_executor(None, dtmf_detector_worker, _buffer, callbacks, loop)
            await asyncio.sleep(0.01)

    def send(self, loop: asyncio.AbstractEventLoop):
        while True:
            if self.__rtp_socket is None or self.__rtp_socket.fileno() < 0:
                break
            start_processing = time.monotonic_ns()

            audio_stream = self.get_audio_stream()
            if not self.is_running.is_set():
                if audio_stream:
                    logger.log(logging.INFO, "Stream ID: %s Set to Done.", audio_stream.stream_id)
                    loop.call_soon_threadsafe(audio_stream.stream_done)
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
                time.sleep(0.02)
                if audio_stream is None:
                    continue
                logger.log(
                    logging.DEBUG,
                    f"Sent all frames from source with id: {audio_stream.stream_id}",
                )
                loop.call_soon_threadsafe(audio_stream.stream_done)
                continue
            
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

    async def receive(self):
        if not self.udp_reader:
            logger.log(logging.CRITICAL, "There is no UdpReader, can't read!")
            return

        while True: 
            try:
                data = await self.udp_reader.read()
                if data is None:
                    logger.log(logging.DEBUG, "Receiver handler stopped.")
                    break

                packet = RtpPacket.parse(data)
                if packet.payload_type == CodecInfo.EVENT:
                    # handle rfc 2833 
                    await self._handle_rfc_2833(packet)
                    await asyncio.sleep(0.01)
                    continue

                if packet.payload_type not in CODECS:
                    logger.log(logging.WARNING, f"Unsupported codecs received, {packet.payload_type}")
                    await asyncio.sleep(0.01)
                    continue

                encoded_frame = self.__jitter_buffer.add(packet)
                # if we have enough encoded buffer then decode
                if encoded_frame:
                    if self.__amd_detector and not self.__amd_detector.amd_started.is_set():
                        self.__amd_detector.amd_started.set()
                    decoded_frame = self.__decoder.decode(encoded_frame.data)
                    for output_q in self._output_queues.values():
                        await output_q.put(decoded_frame)

                await asyncio.sleep(0)

            except asyncio.TimeoutError:
                await asyncio.sleep(0.01)
                continue  # this is neccesary to avoid blocking of checking
                # whether app is runing or not

        # finally put None in to the q to tell stream ended 
        for output_q in self._output_queues.values():
            await output_q.put(None)

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
