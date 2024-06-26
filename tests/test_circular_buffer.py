import pytest
import time
from raspy2mqtt.optoisolated_inputs_handler import CircularBuffer

@pytest.mark.unit
def test_circbuf_push_sample():
    circular_buffer = CircularBuffer(3)
    circular_buffer.push_sample(int(time.time()), 10)
    circular_buffer.push_sample(int(time.time()), 20)
    circular_buffer.push_sample(int(time.time()), 30)
    samples = circular_buffer.get_all_samples()
    assert len(samples) == 3
    assert samples[0][1] == 10
    assert samples[1][1] == 20
    assert samples[2][1] == 30

@pytest.mark.unit
def test_circbuf_circular_behavior():
    circular_buffer = CircularBuffer(3)
    circular_buffer.push_sample(int(time.time()), 10)
    circular_buffer.push_sample(int(time.time()), 20)
    circular_buffer.push_sample(int(time.time()), 30)
    circular_buffer.push_sample(int(time.time()), 40)
    circular_buffer.push_sample(int(time.time()), 50)
    samples = circular_buffer.get_all_samples()
    assert len(samples) == 3
    assert samples[0][1] == 30
    assert samples[1][1] == 40
    assert samples[2][1] == 50

@pytest.mark.unit
def test_circbuf_get_last_sample():
    circular_buffer = CircularBuffer(3)
    assert circular_buffer.get_last_sample() == None
    circular_buffer.push_sample(int(time.time()), 10)
    circular_buffer.push_sample(int(time.time()), 20)
    assert circular_buffer.get_last_sample()[1] == 20
    circular_buffer.push_sample(int(time.time()), 30)
    circular_buffer.push_sample(int(time.time()), 40)
    circular_buffer.push_sample(int(time.time()), 50)
    assert circular_buffer.get_last_sample()[1] == 50
    circular_buffer.push_sample(int(time.time()), 60)
    assert circular_buffer.get_last_sample()[1] == 60

@pytest.mark.unit
def test_circbuf_clear():
    circular_buffer = CircularBuffer(3)
    circular_buffer.push_sample(int(time.time()), 10)
    circular_buffer.push_sample(int(time.time()), 20)
    circular_buffer.clear()
    assert circular_buffer.get_all_samples() == None
    assert circular_buffer.get_last_sample() == None
