import asyncio
import io

from PySIP import _print_debug_info

from .CustomCommuicate import CommWithPauses


class CallHandler:
    def __init__(self, call) -> None:
        self.call = call
        self.rtp_session = call.rtp_session
        self.audio_queue = asyncio.Queue()
        self.previous_stream: AudioStream = None
        _print_debug_info("CallHandler has been initialized..")

    async def say(self, text: str):
        self.audio_bytes = CommWithPauses(text=text)
        self.audio_stream = AudioStream(self.audio_bytes)
        await self.audio_queue.put(self.audio_stream)

        return self.audio_stream

    async def play(self, input_audio: bytes):
        """Simple method to play an audio in call"""
        self.audio_stream = AudioStream(input_audio)
        await self.audio_queue.put(AudioStream(input_audio))

        return self.audio_stream

    async def gather(self, length: int = 1):
        """This method gathers a dtmf tone with the specified
        length and then returns when done"""
        pass

    def gather_and_say(self, text: str, length: int = 1):
        """This method waits for dtmf keys and then if received
        it instantly send it"""
        pass

    async def send_handler(self):
        while self.call.client.is_running:
            if self.previous_stream and self.previous_stream.readable():
                continue

            restult = await self.audio_queue.get()
            self.previous_stream = restult
            self.rtp_session.send_from_source(restult)


class AudioStream(io.BytesIO):
    def __init__(self, initial_bytes = ...) -> None:
        super().__init__(initial_bytes)

    def read_frames(self, nframes: int | None = None):
        return self.read(nframes)

    def drain(self):
        self.read()
        self.seek(0)
