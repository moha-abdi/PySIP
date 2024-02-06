import asyncio
from PySIP.sip_call import SipCall
from PySIP.sip_client import SipClient

# client = SipClient(
#     '111',
#     '192.168.1.112:5060',
#     'UDP',
#     '12345678'
# )
#
# client2 = SipClient(
#     '3001',
#     '192.168.1.112:5060',
#     'UDP',
#     '30013001'
# )

call = SipCall(
    '111',
    '123456789', 
    '192.168.1.112:5060',
    '3001'
)

async def stop_client(client_):
    await asyncio.sleep(8)
    await client_.stop()

async def main():
    # asyncio.get_event_loop().set_debug(True)
    # client_task = asyncio.create_task(client.run())
    # stop_task = asyncio.create_task(stop_client(client))
    #
    # client2_task = asyncio.create_task(client2.run())
    # stop2_task = asyncio.create_task(stop_client(client2))
    #
    call_task = asyncio.create_task(call.start())
    stop3_task = asyncio.create_task(stop_client(call))

    await asyncio.gather(call_task, stop3_task)

asyncio.run(main())
