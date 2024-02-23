from typing import Any, List, Optional

MAX_MISORDER = 100


class JitterFrame:
    def __init__(self, data: bytes, timestamp: int) -> None:
        self.data = data
        self.timestamp = timestamp


class JitterBuffer:
    def __init__(
        self, capacity: int, prefetch: int = 0, is_video: bool = False
    ) -> None:
        assert capacity & (capacity - 1) == 0, "capacity must be a power of 2"
        self._capacity = capacity
        self._origin: Optional[int] = None
        self._packets: List[Any] = [None for _ in range(capacity)]
        self._prefetch = prefetch

    @property
    def capacity(self) -> int:
        return self._capacity

    def add(self, packet) -> Optional[JitterFrame]:
        if self._origin is None:
            self._origin = packet.sequence_number
            delta = 0
            misorder = 0
        else:
            delta = (packet.sequence_number + -self._origin) & 0xFFFF
            misorder = (self._origin + -packet.sequence_number) & 0xFFFF

        if misorder < delta:
            if misorder >= MAX_MISORDER:
                self.remove(self.capacity)
                self._origin = packet.sequence_number
                delta = misorder = 0
            else:
                return None

        if delta >= self.capacity:
            # remove just enough frames to fit the received packets
            excess = delta - self.capacity + 1
            if self.smart_remove(excess):
                self._origin = packet.sequence_number

        pos = packet.sequence_number % self._capacity
        self._packets[pos] = packet

        return self._remove_frame(packet.sequence_number)

    def _remove_frame(self, sequence_number: int) -> Optional[JitterFrame]:
        frame = None
        frames = 0
        packets = []
        remove = 0
        timestamp = None
        assert self._origin is not None

        for count in range(self.capacity):
            pos = (self._origin + count) % self._capacity
            packet = self._packets[pos]
            if packet is None:
                break
            if timestamp is None:
                timestamp = packet.timestamp
            elif packet.timestamp != timestamp:
                # we now have a complete frame, only store the first one
                if frame is None:
                    frame = JitterFrame(
                        data=b"".join([x.payload for x in packets]), timestamp=timestamp
                    )
                    remove = count

                # check we have prefetched enough
                frames += 1
                if frames >= self._prefetch:
                    self.remove(remove)
                    return frame

                # start a new frame
                packets = []
                timestamp = packet.timestamp

            packets.append(packet)

        return None

    def remove(self, count: int) -> None:
        assert count <= self._capacity
        assert self._origin is not None
        for i in range(count):
            pos = self._origin % self._capacity
            self._packets[pos] = None
            self._origin = (self._origin + 1) & 0xFFFF

    def smart_remove(self, count: int) -> bool:
        """
        Makes sure that all packages belonging to the same frame are removed
        to prevent sending corrupted frames to the decoder.
        """
        timestamp = None
        assert self._origin is not None
        for i in range(self._capacity):
            pos = self._origin % self._capacity
            packet = self._packets[pos]
            if packet is not None:
                if i >= count and timestamp != packet.timestamp:
                    break
                timestamp = packet.timestamp
            self._packets[pos] = None
            self._origin = (self._origin + 1) & 0xFFFF
            if i == self._capacity - 1:
                return True
        return False
