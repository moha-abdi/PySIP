import asyncio
import audioop
from dataclasses import dataclass
from enum import Enum, auto
import time
import janus
import numpy as np

from ..filters import PayloadType
from .silence_detection import SilenceDetection


@dataclass
class DefaultSettings:
    initial_silence: int = 2500
    greeting: int = 1500
    after_greeting_silence: int = 800
    total_analysis_time: int = 5000
    minimum_word_length: int = 100
    between_words_silence: int = 50
    maximum_number_of_words: int = 2
    silence_threshold: int = 256
    maximum_word_length: int = 5000


class AmdStatus(Enum):
    HUMAN = auto()
    MACHINE = auto()
    NOTSURE = auto()
    HANGUP = auto()


class AmdState(Enum):
    SILENCE = 1
    WORD = 2


class AnswringMachineDetector:
    def __init__(self) -> None:
        self.settings = DefaultSettings()

        # Find lowest ms value, that will be max wait time for a frame
        self.max_wait_time_for_frame = min(
            self.settings.initial_silence,
            self.settings.greeting,
            self.settings.after_greeting_silence,
            self.settings.total_analysis_time,
            self.settings.minimum_word_length,
            self.settings.between_words_silence,
        )
        self.amd_started = asyncio.Event()
        self.DEFAULT_SAMPLES_PER_MS = 8000 / 1000
        self.amd_start_time = time.monotonic_ns() / 1e6
        self.buffer = np.array([], np.uint8)
        self.amd_status = AmdStatus.NOTSURE
        self.amd_state = AmdState.WORD
        self.audio_frame_count = 0
        self.frame_length = 0
        self.dspsilence = 0
        self.silence_duration = 0
        self.consecutive_voice_duration = 0
        self.voice_duration = 0
        self.words_count = 0
        self.frame_queue = janus.Queue()
        self.total_time_ms = 0
        self.silence_detector = SilenceDetection(self.settings.silence_threshold)
        self.in_initial_silence = True
        self.in_greeting = False

    async def run_detector(self):
        # print("Waiting for app to start")
        # await self.amd_started.wait()
        print("App started")
        while True:
            try:
                start_time = time.monotonic_ns() / 1e6
                f = await asyncio.wait_for(
                    self.frame_queue.async_q.get(), self.max_wait_time_for_frame * 2
                )
                end_time = time.monotonic_ns() / 1e6

                # figure out how much we waited
                res = end_time - start_time
                ms = (2 * self.max_wait_time_for_frame) - res

                current_time = time.monotonic_ns() / 1e6
                if (
                    current_time - self.amd_start_time
                ) > self.settings.total_analysis_time:
                    self.amd_status = AmdStatus.NOTSURE
                    if self.audio_frame_count == 0:
                        print("STOPPED DUE TO NOAUDIO DATA")
                        break
                    else:
                        print("NOT SURE DOUT LONGTIME OR NOAUDIO DATA")
                        print("time was: ", current_time - self.amd_start_time)
                        break

                if f.payload_type in [
                    PayloadType.PCMA,
                    PayloadType.PCMU,
                    PayloadType.CN,
                ]:
                    self.audio_frame_count += 1
                    # convert to PCM for consistency

                    data_array = np.array([], np.int16)
                    if f.payload_type == PayloadType.PCMU:
                        data = audioop.ulaw2lin(f.payload, 1)
                        data = audioop.bias(data, 2, 0)
                        data_array = np.frombuffer(data, np.int16)
                        self.buffer = np.concatenate((self.buffer, data_array))
                        self.frame_length = data_array.size / self.DEFAULT_SAMPLES_PER_MS

                    elif f.payload_type == PayloadType.PCMA:
                        data = audioop.alaw2lin(f.payload, 1)
                        data = audioop.bias(data, 2, 0)
                        data_array = np.frombuffer(data, np.int16)
                        self.buffer = np.concatenate((self.buffer, data_array))
                        self.frame_length = data_array.size / self.DEFAULT_SAMPLES_PER_MS

                    else:
                        self.frame_length = ms

                    self.total_time_ms += self.frame_length

                    # if total time exceeds the total analysis time then give up and stop
                    if self.total_time_ms >= self.settings.total_analysis_time:
                        print("THe time is: ", self.total_time_ms)
                        self.amd_status = AmdStatus.NOTSURE
                        print("STOPPED DUE TO TOOLONG TIME")
                        break

                    # feed the frames to the silence detector
                    if f.payload_type not in [PayloadType.PCMA, PayloadType.PCMU]:
                        self.dspsilence += ms

                    else:
                        self.dspsilence = self.silence_detector.detect_silence(
                            data_array
                        )

                    if self.dspsilence > 0:
                        self.silence_duration = self.dspsilence
                        # print("The silence duration is: ", self.silence_duration)

                        # first check
                        if self.silence_duration >= self.settings.between_words_silence:
                            if self.amd_state != AmdState.SILENCE:
                                print("Changed the state to SILENCE")

                            # find words less than minimum_word_length
                            if (
                                self.consecutive_voice_duration
                                < self.settings.minimum_word_length
                            ) and (self.consecutive_voice_duration) > 0:
                                print(
                                    "Short voice duration: ",
                                    self.consecutive_voice_duration,
                                )
                            self.amd_state = AmdState.SILENCE
                            self.consecutive_voice_duration = 0

                        # second check
                        if (
                            self.in_initial_silence
                            and self.silence_duration >= self.settings.initial_silence
                        ):
                            print(
                                f"Ansering MACHINE, silence_duration{self.silence_duration} ; initial_silence {self.in_initial_silence}"
                            )
                            self.amd_status = AmdStatus.MACHINE
                            break

                        # third check
                        if (
                            self.silence_duration
                            >= self.settings.after_greeting_silence
                            and self.in_greeting
                        ):
                            print(
                                f"Human, after_greeting_silence {self.settings.after_greeting_silence} ; silence_duration {self.silence_duration}"
                            )
                            self.amd_status = AmdStatus.HUMAN
                            break

                    else:
                        self.consecutive_voice_duration += self.frame_length
                        self.voice_duration += self.frame_length

                        # If I have enough consecutive voice to say that I am in a Word,
                        # I can only increment the number of words if my previous
                        # state was Silence, which means that I moved into a word.
                        if (
                            self.consecutive_voice_duration
                            >= self.settings.minimum_word_length
                        ) and self.amd_state == AmdState.SILENCE:
                            self.words_count += 1
                            print("Word detected: words_count: ", self.words_count)
                            self.amd_state = AmdState.WORD

                        if (
                            self.consecutive_voice_duration
                            >= self.settings.maximum_word_length
                        ):
                            print(
                                "Maximum word length detected: ",
                                self.consecutive_voice_duration,
                            )
                            self.amd_status = AmdStatus.MACHINE
                            break

                        if self.words_count > self.settings.maximum_number_of_words:
                            print(
                                "Answring machine ; Max num of maximum_number_of_words: ",
                                self.words_count,
                            )
                            self.amd_status = AmdStatus.MACHINE
                            break

                        if (
                            self.in_greeting
                            and self.voice_duration >= self.settings.greeting
                        ):
                            print(
                                "Answring machine; voice_duration {} ;greeting: {}".format(
                                    self.voice_duration, self.settings.greeting
                                )
                            )
                            self.amd_status = AmdStatus.MACHINE
                            break

                        if self.voice_duration >= self.settings.minimum_word_length:
                            if self.silence_duration > 0:
                                print(
                                    "Detected talk; Previous silence_duration",
                                    self.silence_duration,
                                )
                            self.silence_duration = 0

                        if (
                            self.consecutive_voice_duration
                            >= self.settings.minimum_word_length
                            and not self.in_greeting
                        ):
                            # Only go in here once to change the greeting flag
                            # when we detect the 1st word
                            if self.silence_duration > 0:
                                print(
                                    "Before greeting time, silence duration {} ; voice_duration: {}".format(
                                        self.silence_duration, self.voice_duration
                                    )
                                )

                            self.in_initial_silence = False
                            self.in_greeting = True

                else:
                    self.total_time_ms += ms

                    if self.total_time_ms >= self.settings.total_analysis_time:
                        self.amd_status = AmdStatus.NOTSURE
                        print("Stopped due to NOTSURE")
                        break

            except asyncio.TimeoutError:
                # if It took too long to get a frame back. Giving up.
                print("Couldnt read the frame")
                self.amd_status = AmdStatus.NOTSURE
                break

        print("Reason for stopping is: ", self.amd_status)

    def update_packet(self, packet):
        self.frame_queue.sync_q.put(packet)
