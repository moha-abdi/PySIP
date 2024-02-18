import asyncio
import logging
from typing import List, Optional
from wave import Wave_read

from pydub import AudioSegment
from scipy.io.wavfile import io

from .filters import CallState
from .audio_stream import AudioStream
from .utils.async_utils import wait_for
from .utils.logger import logger
from .utils.edge_tts_utils import CommWithPauses
from .exceptions import SIPTransferException


class CallHandler:
    def __init__(self, call) -> None:
        self.call = call
        self.audio_queue: asyncio.Queue = asyncio.Queue()
        self.previous_stream: Optional[AudioStream] = None

    async def say(self, text: str):
        if asyncio.current_task() not in self.call.client.pysip_tasks:
            self.call.client.pysip_tasks.append(asyncio.current_task())

        try:
            self.audio_bytes = await CommWithPauses(text=text).generate_audio(text=text)
            self.audio_stream = AudioStream(self.audio_bytes, self)
            await self.audio_queue.put(("audio", self.audio_stream))
            return self.audio_stream

        except Exception as e:
            logger.log(logging.ERROR, "Error in say: ", e)
            raise e

    async def play(self, file_name: str, format: str = 'wav'):
        """Simple method to play an audio in call"""
        if asyncio.current_task() not in self.call.client.pysip_tasks:
            self.call.client.pysip_tasks.append(asyncio.current_task())

        temp_file = io.BytesIO()
        try:
            decoded_chunk: AudioSegment = AudioSegment.from_file(file_name, format=format)
        except Exception as e: 
            raise e
        decoded_chunk = decoded_chunk.set_channels(1)
        decoded_chunk = decoded_chunk.set_frame_rate(8000)        
        decoded_chunk.export(temp_file, format='wav')

        self.audio_stream = AudioStream(temp_file, self)
        await self.audio_queue.put(("audio", self.audio_stream))

        return self.audio_stream

    async def gather(
        self, length: int = 1, timeout: float = 7.0, finish_on_key=None, stream=None
    ):
        """This method gathers a dtmf tone with the specified
        length and then returns when done"""
        if asyncio.current_task() not in self.call.client.pysip_tasks:
            self.call.client.pysip_tasks.append(asyncio.current_task())

        dtmf_future: asyncio.Future = asyncio.Future()
        dtmf_future.__setattr__("length", length)
        dtmf_future.__setattr__("timeout", timeout)
        dtmf_future.__setattr__("finish_on_key", finish_on_key)
        dtmf_future.__setattr__("stream", stream)
        await self.audio_queue.put(("dtmf", dtmf_future))

        try:
            result = await dtmf_future
            return int(result)
        except asyncio.CancelledError:
            if not dtmf_future.done():
                dtmf_future.cancel()
                try:
                    await dtmf_future
                except asyncio.CancelledError:
                    pass
            
            _task = asyncio.current_task()
            if (_task is not None) and  _task.cancelling() > 0:
                raise

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
        if asyncio.current_task() not in self.call.client.pysip_tasks:
            self.call.client.pysip_tasks.append(asyncio.current_task())

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
        await stream.wait_finished()

        return dtmf_result

    async def gather_and_play(
        self,
        file_name: str,
        format: str = 'wav',
        length: int = 1,
        delay: int = 7,
        loop: int = 3,
        finish_on_key=None,
        loop_audio_file: str = "",
        delay_audio_file: str = "",
    ):
        """This method waits for dtmf keys and then if received
        it instantly send it"""
        if asyncio.current_task() not in self.call.client.pysip_tasks:
            self.call.client.pysip_tasks.append(asyncio.current_task())

        dtmf_result = None
        for _ in range(loop):
            try:
                stream = await self.play(file_name, format)
                dtmf_result = await self.gather(
                    length=length, timeout=delay, finish_on_key=finish_on_key,
                    stream=stream
                )
                if dtmf_result:
                    dtmf_result = dtmf_result
                    return dtmf_result

            except asyncio.TimeoutError:
                if delay_audio_file:
                    await self.play(delay_audio_file, format=format)
                else:
                    await self.say("You did not any keys please try again")
                continue

        if loop_audio_file:
            stream = await self.play(loop_audio_file, format=format)
        else:
            stream = await self.say(f"You failed to enter the key in {loop} tries. Hanging up the call")
        await stream.wait_finished()

        return dtmf_result

    async def transfer_to(self, to: str | int):
        """
        Transfer the call that is currently on-going to the specified `to`
        Args:
            to (str|int): The target phone number to transfer the call to.
        """
        if asyncio.current_task() not in self.call.client.pysip_tasks:
            self.call.client.pysip_tasks.append(asyncio.current_task())

        self.refer_future: asyncio.Future = self.call.refer_future
        self.refer_message = self.call.client.refer_generator(to)
        await self.call.client.send(self.refer_message)

        try:
            result = await asyncio.wait_for(self.refer_future, 5)
            return (result, None)
        
        except asyncio.TimeoutError:
            return (None, "Timed out")

        except SIPTransferException as e:
            return (None, e.description)

        except Exception:
            return (None, "Unknown error")
        

    async def sleep(self, delay: float):
        if asyncio.current_task() not in self.call.client.pysip_tasks:
            self.call.client.pysip_tasks.append(asyncio.current_task())

        await self.audio_queue.put(("sleep", delay))

    async def hangup(self):
        if asyncio.current_task() not in self.call.client.pysip_tasks:
            self.call.client.pysip_tasks.append(asyncio.current_task())

        if self.call.rtp_session:
            await self.call.client.hangup(self.call.rtp_session)

        else:
            raise ValueError("No rtp_session, couldn't hangup")

    @property
    def dtmf_codes(self) -> List[str]:
        """Contains all the dtmf codes from the start of the call."""
        if self.call.dtmf_handler is not None:
            return self.call.dtmf_handler.dtmf_codes
        
        else:
            return []

    @property
    def call_id(self):
        """Retturns the call id of the current call"""
        return self.call.client.call_id
        
    async def send_handler(self):
        try:
            self.call.client.pysip_tasks.append(asyncio.current_task())
            logger.log(logging.INFO, "CallHandler has been initialized..")
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
                            await self.previous_stream.wait_finished()

                        asyncio.get_event_loop().run_in_executor(
                            None, self.call.rtp_session.send_now, result
                        )

                        self.previous_stream = result

                    elif event_type == "sleep":
                        await asyncio.sleep(result)

                    elif event_type == "drain":
                        result.should_stop_streaming.set()

                    elif event_type == "dtmf":
                        stream = None
                        try:
                            length = result.length
                            timeout = result.timeout
                            finish_on_key = result.finish_on_key
                            stream = result.stream
                            logger.log(logging.INFO, "Started to wait for DTMF")
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
                            self.previous_stream = stream
                            if stream:
                                await stream.drain()
                            result.set_result(dtmf_result)

                        except asyncio.TimeoutError:
                            self.previous_stream = stream
                            if stream:
                                await stream.drain()
                            result.set_exception(asyncio.TimeoutError)

                except asyncio.TimeoutError:
                    empty_queue_count += 1
                    if empty_queue_count >= 10:
                        logger.log(
                            logging.WARNING,
                            "Queue has been empty for a while. Exiting the loop."
                        )
                        break

                except asyncio.CancelledError:
                    break

        except asyncio.CancelledError:
            logger.log(logging.DEBUG, "The send handler task has been cancelled")
            pass

