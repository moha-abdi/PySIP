import sys
import os

PROJECT_PATH = os.getcwd()
print(PROJECT_PATH)
sys.path.append(PROJECT_PATH)

import time
from PySIP.rtp_handler import DTMFBuffer, dtmf_detector_worker
import pyaudio
import numpy as np


buffer = DTMFBuffer(duration=1)
p = pyaudio.PyAudio()

stream = p.open(
    8000,
    1,
    pyaudio.paInt16,
    input=True,
    frames_per_buffer=160
)

def test_handle_inband():
    while True:
        data = stream.read(160)

        data_array = np.frombuffer(data, np.int16)
        buffer.buffer = np.concatenate((buffer.buffer, data_array))

        if not (len(buffer.buffer) >= buffer.size):
            time.sleep(0.01)
            continue   

        dtmf_detector_worker(buffer, [], None)
        time.sleep(0.01)


if __name__ == "__main__":
    try:
        print("Listening for DTMF tones...")
        test_handle_inband()
    
    except KeyboardInterrupt:
        print("Stopping audio capture...")

    finally:
        stream.stop_stream()
        stream.close()
        p.terminate()
