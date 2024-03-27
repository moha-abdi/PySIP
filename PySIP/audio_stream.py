import logging
import queue
from .utils.logger import logger
from wave import Wave_read
import asyncio
import uuid


class AudioStream(Wave_read):
    def __init__(self, f) -> None:
        self.stream_done_future: asyncio.Future = asyncio.Future()
        self.stream_id = str(uuid.uuid4())
        super().__init__(f)

        self.audio_length = self.getnframes() / float(self.getframerate())
        self.input_q: queue.Queue = queue.Queue() # Used queue.Queue instead of asyncio.Queue for it's thread-safity

    def recv(self):
        logger.log(logging.DEBUG, f"Started stream now - id ({self.stream_id})")
        while True:
            frame = self.readframes(160) # 80 not 160 so that it can fit 160 samples when encoded
            if not frame:
                logger.log(logging.DEBUG, "Done preparing all frames in AudioStream")
                # put None to the q to indicate end of stream
                self.input_q.put(None)
                break
            self.input_q.put(frame)

    @property
    def audio_length(self):
        """The audio_length property."""
        return self._audio_length

    @audio_length.setter
    def audio_length(self, value):
        self._audio_length = value 

    def stream_done(self):
        if not self.stream_done_future.done():
            self.stream_done_future.set_result("Sream Sent")

    async def wait_finished(self):
        """Wait for the current stream to be fully sent"""
        await self.stream_done_future


