import asyncio


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


async def main():
    queue = asyncio.Queue()

    task_1 = asyncio.create_task(queue_worker(queue))
    await asyncio.sleep(1)
    task_2 = asyncio.create_task(queue_puttere(queue))
    await asyncio.sleep(0.01)
    queue.task_done()
    print('done')


asyncio.run(main())
