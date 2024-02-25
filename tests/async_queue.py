import asyncio
import time


async def queue_worker(queue: asyncio.Queue):
    for _ in range(100):
        try:

            res = await queue.get()
            print("received res is: ", res)
        except Exception as e:
            print(e)

async def queue_puttere(queue):
    for _ in range(1000):
        await queue.put(_)

def wait_for(condition, timeout=1):
    start = time.time()
    while time.time() - start < timeout:
        try:
            if condition():
                return True
        except Exception as e:
            print(f"Error: {e}")
            
        time.sleep(0.1)
        
    return False

async def cbb(res):
    print(res)
async def main():
    queue = asyncio.Queue()

    task_1 = asyncio.create_task(queue_worker(queue))
    await asyncio.sleep(1)
    task_2 = asyncio.create_task(queue_puttere(queue))
    await asyncio.sleep(0.01)
    queue.task_done()
    print('done')

    q = asyncio.Queue()
    # r = wait_for(q.get_nowait(), 1)
    # print(r)
    values = [1, 2, 3]
    x = [values if values else []]
    for v in x:
        print(v)
    await asyncio.gather(*[])

asyncio.run(main())






