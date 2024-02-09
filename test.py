import asyncio
from PySIP.sip_call import SipCall
from PySIP.sip_client import SipClient
from PySIP.sip_core import DialogState

client = SipClient(
    '111',
    '192.168.1.112:5060',
    'UDP',
    '12345678'
)
#
# client2 = SipClient(
#     '3001',
#     '192.168.1.112:5060',
#     'UDP',
#     '30013001'
# )

call = SipCall(
    '111',
    '12345678', 
    '192.168.1.112:5060',
    '3001'
)

@call.on_call_state_changed
async def call_state_changed(state):
    print("the call was hanged up: ", state)

async def stop_client(client_):
    await asyncio.sleep(19)
    await client_.stop()
    return

async def answered(event):
    print(event)
    await event.wait()
    print("Call has been answered my boy")

async def main():
    asyncio.get_event_loop().set_debug(True)
    client_task = asyncio.create_task(client.run())
    stop_task = asyncio.create_task(stop_client(client))
    #
    # client2_task = asyncio.create_task(client2.run())
    # stop2_task = asyncio.create_task(stop_client(client2))
    #
    call_task = asyncio.create_task(call.start())
    stop3_task = asyncio.create_task(stop_client(call))

    await asyncio.gather(client_task, stop_task, call_task, stop3_task)

asyncio.run(main())
