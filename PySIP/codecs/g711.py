from abc import ABC, abstractmethod
import audioop
from .base import Decoder, Encoder


SAMPLE_RATE = 8000
SAMPLE_WIDTH = 2 # 16 bits
SAMPLES_PER_FRAME = 160


class PcmEncoder(ABC, Encoder):
    @staticmethod
    @abstractmethod 
    def _convert(data: bytes, width: int) -> bytes:
        pass

    def encode(self, frame) -> bytes:
        return self._convert(frame, SAMPLE_WIDTH)


class PcmDecoder(ABC, Decoder):
    @staticmethod
    @abstractmethod 
    def _convert(data: bytes, width: int) -> bytes:
        pass

    def decode(self, frame) -> bytes:
        return self._convert(frame, SAMPLE_WIDTH)


class PcmaEncoder(PcmEncoder):
    @staticmethod
    def _convert(data: bytes, width: int) -> bytes:
        return audioop.lin2alaw(data, width)


class PcmaDecoder(PcmDecoder):
    @staticmethod
    def _convert(data: bytes, width: int) -> bytes:
        return audioop.alaw2lin(data, width)


class PcmuEncoder(PcmaEncoder):
    @staticmethod
    def _convert(data: bytes, width: int) -> bytes:
        return audioop.lin2ulaw(data, width)


class PcmuDecoder(PcmDecoder):
    @staticmethod
    def _convert(data: bytes, width: int) -> bytes:
        return audioop.ulaw2lin(data, width)
