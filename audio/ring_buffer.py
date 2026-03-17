from __future__ import annotations

from array import array
from collections import deque


class AudioRingBuffer:
    def __init__(self, capacity: int):
        self.capacity = max(1, capacity)
        self.chunks = deque()
        self.head_offset = 0
        self.size = 0

    def clear(self):
        self.chunks.clear()
        self.head_offset = 0
        self.size = 0

    def write(self, samples):
        if not samples:
            return

        self.chunks.append(samples)
        self.size += len(samples)

        while self.size > self.capacity and self.chunks:
            excess = self.size - self.capacity
            head = self.chunks[0]
            available = len(head) - self.head_offset

            if excess < available:
                self.head_offset += excess
                self.size -= excess
                break

            self.chunks.popleft()
            self.size -= available
            self.head_offset = 0

    def available(self) -> int:
        return self.size

    def read(self, count: int) -> array:
        count = min(max(0, count), self.size)
        out = array("h")

        while count > 0 and self.chunks:
            head = self.chunks[0]
            available = len(head) - self.head_offset
            take = min(count, available)
            out.extend(head[self.head_offset:self.head_offset + take])
            self.head_offset += take
            self.size -= take
            count -= take

            if self.head_offset >= len(head):
                self.chunks.popleft()
                self.head_offset = 0

        return out
