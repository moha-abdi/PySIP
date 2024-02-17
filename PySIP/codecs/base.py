from abc import ABCMeta, abstractmethod


class Encoder(metaclass=ABCMeta):
    @abstractmethod 
    def encode(self, frame) -> bytes:
        pass


class Decoder(metaclass=ABCMeta):
    @abstractmethod 
    def decode(self, frame) -> bytes:
        pass
