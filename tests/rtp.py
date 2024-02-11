
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
