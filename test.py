import asyncio
import logging
import uuid
from aiodebug import log_slow_callbacks
from PySIP.filters import SIPStatus
from PySIP.sip_call import SipCall
from PySIP.sip_client import SipClient
from PySIP.call_handler import CallHandler
from scripts.BankOTP import call_flow as new_call_flow

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
    '112'
)

@call.on_call_state_changed
async def call_state_changed(state):
    pass

@call.on_call_hanged_up
async def call_stopped(reason):
    pass

@call.on_frame_received 
async def frame_received(frame):
    pass

@call.on_dtmf_received 
async def dtmf_received(dtmf_key):
    print("Received dtmf key: ", dtmf_key)

@call.on_amd_state_received 
async def amd_received(amd_state):
    print("The amd state is: ", amd_state)

@call.on_transfer_state_changed 
async def transfer_state(state):
    print("Transfer state: ", state)
    # for example you can hangup on succesful transfer 
    if state is SIPStatus.OK:
        await call.call_handler.hangup()

async def stop_client(client_):
    await asyncio.sleep(30)
    await client_.stop()
    return

async def answered(event):
    print(event)
    await event.wait()
    print("Call has been answered my boy")


async def call_flow():
    await call.call_handler.say("Hello and welcome there Moha Abdi")
    stream = await call.call_handler.say("Well today was kind of a beautiful day")
    await stream.wait_finished()
    await call.call_handler.transfer_to(3001)
    await call.call_handler.hangup()
    await client.stop()

async def main():
    asyncio.get_event_loop().set_debug(True)
    client_task = asyncio.create_task(client.run())
    # stop_task = asyncio.create_task(stop_client(client))
    #
    # client2_task = asyncio.create_task(client2.run())
    # stop2_task = asyncio.create_task(stop_client(client2))
    #
    call_task = asyncio.create_task(call.start())
    # stop3_task = asyncio.create_task(stop_client(call))
 
    await asyncio.gather(client_task, call_task, call_flow(), return_exceptions=False
                         )
    # call.get_recorded_audio('moha.wav')
    call.get_recorded_audio(f'call_{str(uuid.uuid4())}.wav')

log_slow_callbacks.enable(0.02)
asyncio.run(main())
