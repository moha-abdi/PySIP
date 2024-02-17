from typing import Optional
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
