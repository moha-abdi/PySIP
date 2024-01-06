from scipy.io import wavfile
import numpy as np
from scipy.signal import spectrogram

# Re-import the necessary functions and constants
# Constants for DTMF decoding
DTMF_TONES = {
    (697, 1209): '1', (697, 1336): '2', (697, 1477): '3', (697, 1633): 'A',
    (770, 1209): '4', (770, 1336): '5', (770, 1477): '6', (770, 1633): 'B',
    (852, 1209): '7', (852, 1336): '8', (852, 1477): '9', (852, 1633): 'C',
    (941, 1209): '*', (941, 1336): '0', (941, 1477): '#', (941, 1633): 'D'
}

def dtmf_decode(signal, rate, frame_size=2048, frame_stride=1024, time_threshold=0.4):
    """
    A DTMF decoding function from an audio. Its useful when gathering dtmf directly from the audio if the sip peer doesn't support Telephone event.
    """
    # Frequencies for DTMF tones
    low_freqs = [697, 770, 852, 941]
    high_freqs = [1209, 1336, 1477, 1633]

    # Calculate the spectrogram
    f, t, Sxx = spectrogram(signal, fs=rate, window='hann', nperseg=frame_size, noverlap=frame_stride)
    detected_digits = []
    last_digit_time = -time_threshold  # Initialize to a value that allows the first digit to be detected

    for i in range(len(t)):
        current_time = t[i]
        slice_ = Sxx[:, i]
        peaks = np.argsort(slice_)[-8:]  # Top 8 peaks

        detected_low_freqs = [freq for freq in low_freqs if np.any(np.isclose(f[peaks], freq, atol=10))]
        detected_high_freqs = [freq for freq in high_freqs if np.any(np.isclose(f[peaks], freq, atol=10))]

        if len(detected_low_freqs) == 1 and len(detected_high_freqs) == 1:
            digit = DTMF_TONES[(detected_low_freqs[0], detected_high_freqs[0])]
            # Check if enough time has passed since the last identical digit was detected
            if not detected_digits or digit != detected_digits[-1] or current_time - last_digit_time > time_threshold:
                detected_digits.append(digit)
                last_digit_time = current_time

    return detected_digits

