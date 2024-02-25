import numpy as np
import numpy.typing as npt

class SilenceDetection:
    def __init__(self, silence_threshold) -> None:
        self.silence_threshold = silence_threshold
        self.total_silence = 0

    def detect_silence(self, frame: npt.NDArray[np.int16]):
        if frame.size <= 0:
            return 0 # to avoid division by zero
        accum = np.sum(np.abs(frame))
        accum /= frame.size

        if accum < self.silence_threshold:
            # print("The accum is: ", accum)
            # frame is silent
            self.total_silence += (frame.size / 8000) * 1000
            # here we used 8000 as we already know the
            # samplerate that we will pass here, and we
            # also multipled by 1000 to convert it to ms

        else:
            # No silence detected
            self.total_silence = 0
        
        return self.total_silence

