import asyncio
from wave import Wave_read

from PySIP import _print_debug_info
from .filters import CallState
from .CustomCommuicate import CommWithPauses


class CallHandler:
    def __init__(self, call) -> None:
        self.call = call
        self.audio_queue = asyncio.Queue()
        self.previous_stream: AudioStream = None

    async def say(self, text: str):
        self.audio_bytes = await CommWithPauses(text=text).generate_audio(text=text)
        self.audio_stream = AudioStream(self.audio_bytes)
        await self.audio_queue.put(("audio", self.audio_stream))

        return self.audio_stream

    async def play(self, input_audio: bytes):
        """Simple method to play an audio in call"""
        self.audio_stream = AudioStream(input_audio)
        await self.audio_queue.put(AudioStream(input_audio))

        return self.audio_stream

    async def gather(self, length: int = 1, timeout: float = 7.0) -> int:
        """This method gathers a dtmf tone with the specified
        length and then returns when done"""
        dtmf_future = asyncio.Future()
        dtmf_future.__setattr__("length", length)
        dtmf_future.__setattr__("timeout", timeout)
        await self.audio_queue.put(("dtmf", dtmf_future))

        result = await dtmf_future
        return int(result)

    def gather_and_say(self, text: str, length: int = 1):
        """This method waits for dtmf keys and then if received
        it instantly send it"""
        pass

    async def hangup(self):
        if self.call.rtp_session:
            await self.call.client.hangup(self.call.rtp_session)
            await self.call.client.cleanup()

        else:
            raise ValueError("No rtp_session, couldn't hangup")

    async def send_handler(self):
        try:
            _print_debug_info("CallHandler has been initialized..")
            empty_queue_count = 0  # Counter for consecutive empty queue checks

            while True:
                await asyncio.sleep(0.1)

                if self.call.call_state is not CallState.ANSWERED:
                    continue

                if not self.call.client.is_running:
                    break  # Exit the loop if the client is not running

                if not self.call.rtp_session:
                    continue

                try:
                    event_type, result = await asyncio.wait_for(
                        self.audio_queue.get(), timeout=1.0
                    )
                    empty_queue_count = 0  # Reset the counter if an item is retrieved

                    if event_type == "audio":
                        self.call.rtp_session.send_from_source(result)

                    elif event_type == "dtmf":
                        try:
                            length = result.length
                            timeout = result.timeout
                            dtmf_result = await asyncio.wait_for(
                                self.call.dtmf_handler.get_dtmf(length), timeout
                            )
                            result.set_result(dtmf_result)

                        except asyncio.TimeoutError:
                            result.set_exception(asyncio.TimeoutError)

                except asyncio.TimeoutError:
                    empty_queue_count += 1
                    if empty_queue_count >= 10:
                        _print_debug_info(
                            "Queue has been empty for a while. Exiting the loop."
                        )
                        break

        except asyncio.CancelledError:
            pass


class AudioStream(Wave_read):
    def __init__(self, f) -> None:
        self.audio_sent_future = asyncio.Future()
        super().__init__(f)

    def drain(self):
        """This ensures that any remains of the current stream is dropped"""
        self.setpos(0)
        self.readframes(self.getnframes())

    async def flush(self):
        await self.audio_sent_future

    def __repr__(self) -> str:
        return str(id(self))
