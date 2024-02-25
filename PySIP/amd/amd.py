import asyncio
import audioop
from dataclasses import dataclass
from enum import Enum, auto
import logging
import time
import numpy as np

from ..codecs.codec_info import CodecInfo
from .silence_detection import SilenceDetection
from ..utils.logger import logger


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
        self.amd_status = AmdStatus.NOTSURE
        self.amd_state = AmdState.WORD
        self.audio_frame_count = 0
        self.frame_length = 0
        self.dspsilence = 0
        self.silence_duration = 0
        self.consecutive_voice_duration = 0
        self.voice_duration = 0
        self.words_count = 0
        self.total_time_ms = 0
        self.silence_detector = SilenceDetection(self.settings.silence_threshold)
        self.in_initial_silence = True
        self.in_greeting = False

    async def run_detector(self, input_q: asyncio.Queue, _callbacks):
        await self.amd_started.wait()
        logger.log(logging.DEBUG, "AMD app started")
        while True:
            try:
                start_time = time.monotonic_ns() / 1e6
                data = await asyncio.wait_for(
                    input_q.get(), self.max_wait_time_for_frame * 2
                )
                end_time = time.monotonic_ns() / 1e6

                # figure out how much we waited
                res = end_time - start_time
                ms = int((2 * self.max_wait_time_for_frame) - res)
                # if we fail to read in a frame it means call hanged up
                if data is None:
                    logger.log(logging.INFO, "Amd Stopped. REASON: Call Hanged Up")
                    self.amd_status = AmdStatus.HANGUP
                    break

                current_time = time.monotonic_ns() / 1e6
                if (
                    current_time - self.amd_start_time
                ) > self.settings.total_analysis_time:
                    self.amd_status = AmdStatus.NOTSURE
                    if self.audio_frame_count == 0:
                        logger.log(logging.DEBUG, "Amd Stopped. REASON: No audio data")
                        break
                    else:
                        logger.log(logging.DEBUG, "Amd Stopped. REASON: NO audio data or long time")
                        break

                
                self.audio_frame_count += 1
                # convert to PCM for consistency

                data_array = np.array([], np.int16)
                data_array = np.frombuffer(data, np.int16)
                self.frame_length = data_array.size / self.DEFAULT_SAMPLES_PER_MS 
                self.total_time_ms += self.frame_length

                # if total time exceeds the total analysis time then give up and stop
                if self.total_time_ms >= self.settings.total_analysis_time:
                    self.amd_status = AmdStatus.NOTSURE
                    logger.log(logging.DEBUG, "Amd Stopped. REASON: Too Long time")
                    break

                # feed the frames to the silence detector
                loop = asyncio.get_event_loop()
                self.dspsilence = await loop.run_in_executor(
                      None,
                      self.silence_detector.detect_silence,
                      data_array
                )

                if self.dspsilence > 0:
                    self.silence_duration = self.dspsilence

                    # first check
                    if self.silence_duration >= self.settings.between_words_silence:
                        if self.amd_state != AmdState.SILENCE:
                            logger.log(logging.DEBUG, "AmdState Changed the state to SILENCE")

                        # find words less than minimum_word_length
                        if (
                            self.consecutive_voice_duration
                            < self.settings.minimum_word_length
                        ) and (self.consecutive_voice_duration) > 0:
                            logger.log(
                                logging.DEBUG,
                                "Amd Got Short voice duration: {}".format(
                                    self.consecutive_voice_duration
                                )
                            )
                        self.amd_state = AmdState.SILENCE
                        self.consecutive_voice_duration = 0

                    # second check
                    if (
                        self.in_initial_silence
                        and self.silence_duration >= self.settings.initial_silence
                    ):
                        logger.log(
                            logging.INFO,
                            f"Ansering Machine Detected, silence_duration{self.silence_duration} -- initial_silence {self.in_initial_silence}"
                        )
                        self.amd_status = AmdStatus.MACHINE
                        break

                    # third check
                    if (
                        self.silence_duration
                        >= self.settings.after_greeting_silence
                        and self.in_greeting
                    ):
                        logger.log(
                            logging.INFO,
                            f"Human Detected, after_greeting_silence {self.settings.after_greeting_silence} -- silence_duration {self.silence_duration}"
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
                        logger.log(logging.DEBUG, f"Amd Detected a Word -- words_count: {self.words_count}")
                        self.amd_state = AmdState.WORD

                    if (
                        self.consecutive_voice_duration
                        >= self.settings.maximum_word_length
                    ):
                        logger.log(
                            logging.DEBUG,
                            "Amd Detected Maximum word length: {}".format(
                                self.consecutive_voice_duration
                            )
                        )
                        self.amd_status = AmdStatus.MACHINE
                        break

                    if self.words_count > self.settings.maximum_number_of_words:
                        logger.log(
                            logging.INFO,
                            f"Answring Machine Detected -- Max num of maximum_number_of_words: {self.words_count}"
                        )
                        self.amd_status = AmdStatus.MACHINE
                        break

                    if (
                        self.in_greeting
                        and self.voice_duration >= self.settings.greeting
                    ):
                        logger.log(
                            logging.INFO,
                            "Answring Machine Detected -- voice_duration {} -- greeting: {}".format(
                                self.voice_duration, self.settings.greeting
                            )
                        )
                        self.amd_status = AmdStatus.MACHINE
                        break

                    if self.voice_duration >= self.settings.minimum_word_length:
                        if self.silence_duration > 0:
                            logger.log(
                                logging.DEBUG,
                                "Amd Detected Talk -- Previous silence_duration: {}".format(
                                    self.silence_duration
                                )
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
                            logger.log(
                                logging.DEBUG,
                                "Amd Before greeting time, silence duration {} -- voice_duration: {}".format(
                                    self.silence_duration, self.voice_duration
                                )
                            )

                        self.in_initial_silence = False
                        self.in_greeting = True 

            except asyncio.TimeoutError:
                # if It took too long to get a frame back. Giving up.
                logger.log(logging.WARNING, "Couldnt read the frame from the input queue")
                self.amd_status = AmdStatus.NOTSURE
                break

        logger.log(logging.INFO, f"Amd Stopped. REASON: {self.amd_status}")
        # Notify the callbacks
        await asyncio.gather(*[_cb(self.amd_status) for _cb in _callbacks])
 
