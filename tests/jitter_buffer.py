import random

# Define a simple JitterBuffer class for simulation
class JitterBuffer:
    def __init__(self, capacity: int):
        self._capacity = capacity
        self._origin = None
        self.MAX_MISORDER = 2  # Maximum allowed misorder for this simulation

    def add(self, packet_sequence_number):
        pli_flag = False

        if self._origin is None:
            self._origin = packet_sequence_number
            delta = 0
            misorder = 0
        else:
            delta = packet_sequence_number - self._origin
            misorder = self._origin - packet_sequence_number

        print(f"Received packet with sequence number: {packet_sequence_number}")
        print(f"Delta: {delta}, Misorder: {misorder}")

        if misorder < delta:
            if misorder >= self.MAX_MISORDER:
                print("Significant misorder detected. Removing excess packets...")
                # Simulate removing excess packets
                self._origin = packet_sequence_number
                delta = misorder = 0
                pli_flag = True  # Simulate setting PLI flag
            else:
                print("Misorder detected, but within acceptable range.")
                return pli_flag, None

        print("Packet added to buffer.")
        return pli_flag, packet_sequence_number

# Simulate packet sequence with potential misorder and wraparound
packet_sequence = list(range(10))
random.shuffle(packet_sequence)

# Create JitterBuffer instance
jitter_buffer = JitterBuffer(capacity=10)

# Simulate adding packets to the buffer
for sequence_number in packet_sequence:
    pli_flag, _ = jitter_buffer.add(sequence_number)
    if pli_flag:
        print("PLI flag set.")


x = 65535
y = 65537

print((x + y) & 65535)
print((x + y) % 65535)
print(1 + -2)
