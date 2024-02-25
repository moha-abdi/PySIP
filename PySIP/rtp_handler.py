import asyncio
import audioop
from enum import Enum
import logging
import random
from struct import unpack, unpack_from
import time
from typing import Callable, Dict, List, Optional, Union
import wave
from PySIP.amd.amd import AnswringMachineDetector

from PySIP.exceptions import AudioStreamError, NoSupportedCodecsFound
from PySIP.jitter_buffer import JitterBuffer
from .audio_stream import AudioStream
from .udp_handler import open_udp_connection
from .utils.logger import logger
from .codecs import get_encoder, get_decoder, CODECS
from .codecs.codec_info import CodecInfo


MAX_WAIT_FOR_STREAM = 40  # seconds
RTP_HEADER_LENGTH = 12
RTP_PORT_RANGE = range(10_000, 20_000)
SEND_SILENCE = True # send silence frames when no stream
USE_AMD_APP = True


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

    async def _start(self):
        self.is_running.set()
        logger.log(
            logging.DEBUG,
            f"Establishing RTP Connection with: LOCAL_IP: {self.src_ip} : LOCAL_PORT {self.src_port} -- SERVER_IP: {self.dst_ip} : SERVER_PORT {self.dst_port}",
        )
        self.udp_reader, self.udp_writer = await open_udp_connection(
            (self.dst_ip, self.dst_port), (self.src_ip, self.src_port)
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
            ))
            _tasks.append(amd_task)

        try:
            await asyncio.gather(*_tasks)
        except asyncio.CancelledError:
            if send_task.done():
                pass
            if receive_task.done():
                pass
            if frame_monitor_task.done():
                pass
            if amd_task and amd_task.done():
                pass

            _task = asyncio.current_task()
            if _task and _task.cancelling() > 0:
                raise
        except Exception as e:
            logger.log(logging.ERROR, e, exc_info=True)

        finally:
            if not send_task.done():
                send_task.cancel()
                try:
                    await send_task
                except asyncio.CancelledError:
                    pass

            if not receive_task.done():
                receive_task.cancel()
                try:
                    await receive_task
                except asyncio.CancelledError:
                    pass

            if not frame_monitor_task.done():
                frame_monitor_task.cancel()
                try:
                    await frame_monitor_task
                except asyncio.CancelledError:
                    pass

            if amd_task and not amd_task.done():
                amd_task.cancel()
                try:
                    await amd_task
                except asyncio.CancelledError:
                    pass

    async def _stop(self):
        # close the connections
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

        # check for registered callbacks
        if not self.__callbacks:
            logger.log(logging.DEBUG, "No callbacks passed to RtpHandler.")
            return
        if not (callbacks := self.__callbacks.get('dtmf_callback')):
            return
        # notify the callbacks
        for cb in callbacks:
            await cb(event)

    async def send(self):
        while True:
            start_processing = time.monotonic_ns()

            if not self.is_running.is_set():
                logger.log(logging.DEBUG, "Succesfully stopped the sender worker")
                break

            audio_stream = self.get_audio_stream()
            if not audio_stream and not SEND_SILENCE:
                await asyncio.sleep(0.02)  # avoid busy-waiting
                continue

            try:
                if audio_stream is None:
                    payload = self.generate_silence_frames()
                else:
                    payload = audio_stream.input_q.get_nowait()
            except asyncio.QueueEmpty:
                await asyncio.sleep(0.02)
                continue

            # if all frames are sent then continue
            if not payload:
                await asyncio.sleep(0)
                if audio_stream is None:
                    continue
                logger.log(
                    logging.DEBUG,
                    f"Sent all frames from source with id: {audio_stream.stream_id}",
                )
                audio_stream.stream_done()
                continue

            encoded_payload = self.__encoder.encode(payload)
            packet = RtpPacket(
                payload_type=self.selected_codec,
                payload=encoded_payload,
                sequence_number=self.__sequence_number,
                timestamp=self.__timestamp,
                ssrc=self.ssrc,
            ).serialize()
            await self.udp_writer.write(packet)

            delay = (1 / self.selected_codec.rate) * 160
            processing_time = (time.monotonic_ns() - start_processing) / 1e9
            sleep_time = delay - processing_time
            self.__sequence_number = (self.__sequence_number + 1) % 65535  # Wrap around at 2^16 - 1
            self.__timestamp = (self.__timestamp + len(encoded_payload)) % 4294967295  # Wrap around at 2^32 -1

            await asyncio.sleep(sleep_time)

    async def receive(self):
        while True:
            await asyncio.sleep(0.01)
            if not self.is_running.is_set():
                logger.log(logging.DEBUG, "Receiver handler stopped.")
                break

            if not self.udp_reader:
                logger.log(logging.CRITICAL, "There is no UdpReader, can't read!")
                return
            try:
                data = await asyncio.wait_for(self.udp_reader.read(4096), 0.5)
                packet = RtpPacket.parse(data)

                if packet.payload_type == CodecInfo.EVENT:
                    # handle rfc 2833 
                    await self._handle_rfc_2833(packet)
                    continue

                if packet.payload_type not in CODECS:
                    logger.log(logging.WARNING, f"Unsupported codecs received, {packet.payload_type}")
                    continue
                encoded_frame = self.__jitter_buffer.add(packet) 

                # if we have enough encoded buffer then decode
                if encoded_frame:
                    if self.__amd_detector and not self.__amd_detector.amd_started.is_set():
                        self.__amd_detector.amd_started.set()
                    loop = asyncio.get_event_loop()
                    loop.run_in_executor(None, decoder_worker, (packet.payload_type, encoded_frame), self._output_queues, loop)

            except asyncio.TimeoutError:
                continue  # this is neccesary to avoid blocking of checking
                # whether app is runing or not

        # finally put None in to the q to tell stream ended 
        loop = asyncio.get_event_loop()
        loop.run_in_executor(None, decoder_worker, (None, None), self._output_queues, loop)

    async def frame_monitor(self):
        # first add stream queue to the output _output_queues
        self._output_queues['frame_monitor'] = stream_q = asyncio.Queue()
        self._output_queues['new'] = asyncio.Queue()
        while True:
            await asyncio.sleep(0.01)
            if not self.is_running.is_set():
                break
            if not self.__callbacks:
                logger.log(logging.DEBUG, "No callbacks passed to RtpHandler.")
                break
            try:
                frame = stream_q.get_nowait()
                if not (callbacks := self.__callbacks.get('frame_monitor')):
                    break
                # check for registered callbacks
                for cb in callbacks:
                    await cb(frame)

            except asyncio.QueueEmpty:
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
