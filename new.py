import asyncio
import time
from PySIP.call_handler import AudioStream
from PySIP.CustomCommuicate import CommWithPauses

def reader(source: AudioStream):
    read_frames = 0
    while True:
        time.sleep(0)
        if source.should_stop_streaming.is_set():
            print("partial", read_frames)
            break

        frame = source.readframes(160)
        read_frames += 160

        if not frame:
            print("Read all frames: ", read_frames)
            break



async def main():
    stream = await CommWithPauses("hello").generate_audio("Hello this is  atest and it should last more than two seonds the other one was too short you are good boy")
    stream = AudioStream(stream)
    asyncio.get_event_loop().run_in_executor(None, reader, stream)
    print("sleeping for 2 seconds")
    await asyncio.sleep(0.3)
    await stream.drain()

asyncio.run(main())
