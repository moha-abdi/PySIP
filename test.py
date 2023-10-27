from PySIP.call import VOIP
import asyncio


voip = VOIP('13033333096', 'sever:port', password="??")


async def main():
    await voip.call('11111111111', tts=True, text="Hello")

    if voip.received_bytes:
        print('Recorded audio saved to recored.mp3')


asyncio.run(main())