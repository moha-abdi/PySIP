
from .g711 import PcmaDecoder, PcmaEncoder, PcmuDecoder, PcmuEncoder
from .codec_info import CodecInfo


CODECS = [
    CodecInfo.PCMA,
    CodecInfo.PCMU,
    CodecInfo.EVENT
]


def get_encoder(codec: CodecInfo):
    if codec == CodecInfo.PCMA:
        return PcmaEncoder()
    elif codec == CodecInfo.PCMU:
        return PcmuEncoder()
    else:
        raise ValueError(f"No encoder found for: {codec}")

def get_decoder(codec: CodecInfo):
    if codec == CodecInfo.PCMA:
        return PcmaDecoder()
    elif codec == CodecInfo.PCMU:
        return PcmuDecoder()
    else:
        raise ValueError(f"No decoder foun for: {codec}")
