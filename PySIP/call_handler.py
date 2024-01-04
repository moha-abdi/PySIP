import asyncio
from wave import Wave_read

from PySIP import _print_debug_info
from .filters import CallState
from .CustomCommuicate import CommWithPauses
from .utils.async_utils import wait_for


class CallHandler:
    def __init__(self, call) -> None:
        self.call = call
        self.audio_queue = asyncio.Queue()
        self.previous_stream: AudioStream = None

    async def say(self, text: str):
        self.audio_bytes = await CommWithPauses(text=text).generate_audio(text=text)
        self.audio_stream = AudioStream(self.audio_bytes, self)
        await self.audio_queue.put(("audio", self.audio_stream))

        return self.audio_stream

    async def play(self, input_audio: bytes):
        """Simple method to play an audio in call"""
        self.audio_stream = AudioStream(input_audio)
        await self.audio_queue.put(AudioStream(input_audio))

        return self.audio_stream

    async def gather(
        self, length: int = 1, timeout: float = 7.0, finish_on_key=None
    ) -> int:
        """This method gathers a dtmf tone with the specified
        length and then returns when done"""
        dtmf_future = asyncio.Future()
        dtmf_future.__setattr__("length", length)
        dtmf_future.__setattr__("timeout", timeout)
        dtmf_future.__setattr__("finish_on_key", finish_on_key)
        await self.audio_queue.put(("dtmf", dtmf_future))

        result = await dtmf_future
        return int(result)

    async def gather_and_say(
        self,
        length: int = 1,
        delay: int = 7,
        loop: int = 3,
        finish_on_key=None,
        loop_msg: str = "",
        delay_msg: str = "",
    ):
        """This method waits for dtmf keys and then if received
        it instantly send it"""
        dtmf_result = None
        for _ in range(loop):
            try:
                dtmf_result = await self.gather(
                    length=length, timeout=delay, finish_on_key=finish_on_key
                )
                if dtmf_result:
                    dtmf_result = dtmf_result
                    return dtmf_result

            except asyncio.TimeoutError:
                text = delay_msg or "You did not any keys please try again"
                await self.say(text)
                continue

        text = (
            loop_msg
            or f"You failed to enter the key in {loop} tries. Hanging up the call"
        )
        stream = await self.say(text)
        await stream.flush()

        return dtmf_result

    async def sleep(self, delay: float):
        await self.audio_queue.put(("sleep", delay))

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
                    # _print_debug_info(f"Q is got, type {event_type}")
                    empty_queue_count = 0  # Reset the counter if an item is retrieved

                    if event_type == "audio":
                        if self.previous_stream:
                            await self.previous_stream.flush()

                        asyncio.get_event_loop().run_in_executor(
                            None, self.call.rtp_session.send_now, result
                        )

                        self.previous_stream = result

                    elif event_type == "sleep":
                        await asyncio.sleep(result)

                    elif event_type == "drain":
                        result.should_stop_streaming.set()

                    elif event_type == "dtmf":
                        try:
                            length = result.length
                            timeout = result.timeout
                            finish_on_key = result.finish_on_key
                            _print_debug_info("Started to wait for DTMF")
                            awaitable = None

                            if self.previous_stream:
                                asyncio.create_task(
                                    self.call.dtmf_handler.started_typing(
                                        self.previous_stream.drain
                                    )
                                )
                                awaitable = self.previous_stream.audio_sent_future

                            dtmf_result = await wait_for(
                                self.call.dtmf_handler.get_dtmf(length, finish_on_key),
                                timeout,
                                awaitable
                            )
                            result.set_result(dtmf_result)
                            self.previous_stream = None

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
    def __init__(self, f, instance: CallHandler = None) -> None:
        self.audio_sent_future = asyncio.Future()
        self.should_stop_streaming = asyncio.Event()
        self.instance = instance
        super().__init__(f)

        self.audio_length = self.getnframes() / float(self.getframerate())

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
        self.should_stop_streaming.set()

    async def flush(self):
        await self.audio_sent_future

    def __repr__(self) -> str:
        return str(id(self))
