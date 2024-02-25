import asyncio
import time

def new_test(queue, loop):
    time.sleep(4)
    asyncio.run_coroutine_threadsafe(queue.put(8), loop)
    
async def sleep_test():
    queue = asyncio.Queue()
    loop = asyncio.get_event_loop()
    print('going to sleep')
    res = await loop.run_in_executor(None, new_test, queue, loop)
    # time.sleep(5)
    print(await queue.get())
    print('waking up')

async def parallel():
    # run two sleep_tests in parallel and wait until both finish
    await asyncio.gather(sleep_test(), sleep_test())
    x = {'moha': asyncio.Queue()}

    for name, q in x.items():
        print(name)

    y = bytearray()
    print(bytes(y))


    


asyncio.run(parallel())
