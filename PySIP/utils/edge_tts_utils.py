import logging
from typing import Union, Optional
from pydub import AudioSegment
import io
from edge_tts import Communicate
from .logger import logger


class NoPausesFound(Exception):
    def __init__(self, description = None) -> None:
        self.description = (f'No pauses were found in the text. Please '
            + f'consider using `edge_tts.Communicate` instead.')

        super().__init__(self.description)


class CommWithPauses(Communicate):
    """
    This class uses edge_tts to generate text
    but with pauses for example:- text: 'Hello
    this is simple text. [pause: 2s] Paused 2s'
    """
    def __init__(
        self,
        text: str,
        voice: str = "Microsoft Server Speech Text to Speech Voice (en-US, AriaNeural)",
        max_pause: int = 6, # maximum pause time in seconds.
        **kwargs

    ) -> None:
        super().__init__(text, voice, **kwargs)
        self.max_pause = max_pause * 1000
        self.parsed = self.parse_text()
        self.file = io.BytesIO()
        self.target_channels = 1
        self.target_framerate = 8000

    def parse_text(self):
        if not "[pause:" in self.text:
            raise NoPausesFound

        parts = self.text.split("[pause:")
        for part in parts:
            if "]" in part:
                pause_time, content = part.split("]", 1)
                pause_time = self.parse_time(pause_time)

                yield pause_time, content.strip()

            else:
                content = part
                yield 0, content.strip()

    def parse_time(self, time_str: str) -> int:
        if time_str[-2:] == 'ms':
            unit = 'ms'
            time_value = int(time_str[:-2])

            return min(time_value, self.max_pause)

        elif time_str[-1] == 's':
            unit = 's'
            time_value = int(time_str[:-1]) * 1000

            return min(time_value, self.max_pause)

        else:
            raise ValueError(f"Invalid time unit! only m/ms are are allowed")

    async def chunkify(self):
        for pause_time, content in self.parsed:
            if not pause_time and not content:
                pass

            elif not pause_time and content:
                audio_bytes = await self.generate_audio(content)
                self.file.write(audio_bytes)

            elif not content and pause_time:
                pause_bytes = self.generate_pause(pause_time)
                self.file.write(pause_bytes)

            else:
                pause_bytes = self.generate_pause(pause_time)
                audio_bytes = await self.generate_audio(content)
                self.file.write(pause_bytes)
                self.file.write(audio_bytes)

    def generate_pause(self, time: int) -> io.BytesIO:
        """
        pause time should be provided in ms
        """
        temp_file = io.BytesIO()
        silent: AudioSegment = AudioSegment.silent(time, 24000)
        silent.set_channels(self.target_channels)
        silent.set_frame_rate(self.target_framerate)
        silent.export(temp_file, format='wav')
        return temp_file

    async def generate_audio(self, text: str) -> io.BytesIO:
        """
        this genertes the real TTS using edge_tts for this part.
        """
        temp_file = io.BytesIO()
        temp_chunk = io.BytesIO()
        self.text = text
        async for chunk in self.stream():
            if chunk['type'] == 'audio':
                temp_chunk.write(chunk['data'])

        temp_chunk.seek(0)
        decoded_chunk: AudioSegment = AudioSegment.from_mp3(temp_chunk)
        decoded_chunk = decoded_chunk.set_channels(self.target_channels)
        decoded_chunk = decoded_chunk.set_frame_rate(self.target_framerate)
        logger.log(logging.DEBUG, f"audio data -> frame width:-> {decoded_chunk.frame_width} -> samplewidth {decoded_chunk.sample_width} ; framerate -> {decoded_chunk.frame_rate} ; {decoded_chunk.DEFAULT_CODECS}")
        
        decoded_chunk.export(temp_file, format='wav')
        return temp_file

    async def save(
        self,
        audio_fname: Union[str, bytes],
        metadata_fname: Optional[Union[str, bytes]] = None,
    ) -> None:
        """
        Save the audio and metadata to the specified files.
        """
        await self.chunkify()
        await super().save(audio_fname, metadata_fname)

        self.file.seek(0)
        audio: AudioSegment = AudioSegment.from_raw(
            self.file,
            sample_width=2,
            frame_rate=24000,
            channels=1
        )
        audio.export(audio_fname)


