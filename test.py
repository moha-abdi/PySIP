from PySIP.call import VOIP
from PySIP.call_handler import CallHandler
import asyncio


voip = VOIP('184848484488', 'server:port', connection_type='UDP', password="your_password")
call_handler = CallHandler(voip)


async def main():
    await voip.call("1000000000000", tts=True, text="Hello")
    asyncio.create_task(call_handler.send_handler())

    if voip.received_bytes:
        print('Recorded audio saved to recored.mp3')


asyncio.run(main())
