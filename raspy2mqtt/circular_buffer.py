#!/usr/bin/env python3

#
# Author: fmontorsi
# Created: June 2024
# License: Apache license
#


# =======================================================================================================
# CircularBuffer
# =======================================================================================================


class CircularBuffer:
    def __init__(self, size: int):
        self.size = size
        self.buffer = [(None, None)] * size  # buffer is empty at the start
        self.index = 0  # next writable location in the buffer

    def push_sample(self, timestamp: int, value: bool) -> None:
        self.buffer[self.index % self.size] = (timestamp, value)
        self.index += 1

    def get_all_samples(self) -> list:
        if self.index == 0:
            return None  # buffer is empty
        if self.index <= self.size:
            return self.buffer[: self.index]  # return only valid/populated items
        idx_mod = self.index % self.size
        return self.buffer[idx_mod:] + self.buffer[:idx_mod]  # linearize the circular buffer

    def get_last_sample(self) -> tuple:
        if self.index == 0:
            return None  # buffer is empty
        last_index = (self.index - 1) % self.size
        return self.buffer[last_index]

    def clear(self) -> None:
        self.buffer = [(None, None)] * self.size
        self.index = 0
