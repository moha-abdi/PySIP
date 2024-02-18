import logging
from .utils.logger import logger
from wave import Wave_read
import asyncio
import uuid


class AudioStream(Wave_read):
    def __init__(self, f, instance = None) -> None:
        self.audio_sent_future: asyncio.Future = asyncio.Future()
        self.is_running = asyncio.Event()
        self.instance = instance
        self.stream_id = str(uuid.uuid4())
        super().__init__(f)

        self.audio_length = self.getnframes() / float(self.getframerate())
        self.is_running.set()
        self.input_q: asyncio.Queue = asyncio.Queue()

    async def recv(self):
        while True:
            if not self.is_running.set():
                logger.log(logging.INFO, "Stream no longer running.")
                break

            frame = self.readframes(160)
            await self.input_q.put(frame)

    @property
    def audio_length(self):
        """The audio_length property."""
        return self._audio_length

    @audio_length.setter
    def audio_length(self, value):
        self._audio_length = value

    async def drain(self):
        """This ensures that any remains of the current stream is dropped"""
        if self.instance:
            await self.instance.audio_queue.put(("drain", self))
            return
        self.is_running.clear()

    async def wait_finished(self):
        """Wait for the current stream to be fully sent"""
        await self.audio_sent_future


