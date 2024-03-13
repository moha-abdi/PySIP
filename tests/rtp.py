import random
from typing import Optional, Union
num = 65536888 % 65535
print(num)

import time

start = time.monotonic_ns()
st = time.monotonic()

time.sleep(2.3)

en = time.monotonic()
end = time.monotonic_ns()

print((end - start) / 1000000000)
print(en - st)


class TimestampMapper:
    def __init__(self) -> None:
        self._last: Optional[int] = None
        self._origin: Optional[int] = None

    def map(self, timestamp: int) -> int:
        if self._origin is None:
            # first timestamp
            self._origin = timestamp
        elif timestamp < self._last:
            # RTP timestamp wrapped
            self._origin -= 1 << 32
            print("wrapped now")
            print('res is: ', self._origin)

        self._last = timestamp
        return timestamp - self._origin


timestamps = [4294967265, 4294967275, 4294967285, 4294967295, 5, 15, 25]
ts_mapper = TimestampMapper()

for i in range(len(timestamps)):
    res = ts_mapper.map(timestamps[i])
    print(f"tried with: {timestamps[i]}; result is {res}")


out_sequence = [1, 2, 4, 3]
_origin = None

for i in range(len(out_sequence)):
    if not _origin:
        _origin = out_sequence[i]
        delta = 0
        misorder = 0

    else:
        delta = out_sequence[i] - _origin
        misorder = _origin - out_sequence[i]

    print(f"The delta is {delta}, misorder is: {misorder}")


x = range(4, 10)
print(x)

print(random.choice(x))
from enum import Enum


class CodecInfo(Enum):
    def __new__(
        cls,
        value: Union[int, str],
        clock: int = 0,
        channel: int = 0,
        description: str = "",
    ):
        obj = object.__new__(cls)
        obj._value_ = value
        obj.rate = clock
        obj.channel = channel
        obj.description = description
        return obj

    @property
    def rate(self) -> int:
        return self._rate

    @rate.setter
    def rate(self, value: int) -> None:
        self._rate = value

    @property
    def channel(self) -> int:
        return self._channel

    @channel.setter
    def channel(self, value: int) -> None:
        self._channel = value

    @property
    def description(self) -> str:
        return self._description

    @description.setter
    def description(self, value: str) -> None:
        self._description = value

    def __int__(self) -> int:
        try:
            return int(self.value)
        except ValueError:
            pass
        raise Exception(
            self.description + " is a dynamically assigned payload"
        )

    def __str__(self) -> str:
        if isinstance(self.value, int):
            return self.description
        return str(self.value)

    # Audio
    PCMU = 0, 8000, 1, "PCMU"
    GSM = 3, 8000, 1, "GSM"
    G723 = 4, 8000, 1, "G723"
    DVI4_8000 = 5, 8000, 1, "DVI4"
    DVI4_16000 = 6, 16000, 1, "DVI4"
    LPC = 7, 8000, 1, "LPC"
    PCMA = 8, 8000, 1, "PCMA"
supportedd = [CodecInfo.PCMA, CodecInfo.PCMU]

print(' '.join([str(int(supported)) for supported in supportedd]))

x = "a=ssrc:1264272126"
print(int(x.split(' ')[0].split(':')[1]))
ip = "838388"
y = f"c=IN IP4 {ip}\r\n"
print(y.split(' ')[2])
