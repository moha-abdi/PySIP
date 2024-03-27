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
    '3001',
    '192.168.1.112:5060',
    'UDP',
    '30013001'
)

call = SipCall(
    '3001',
    '30013001', 
    '192.168.1.112:5060',
    '111'
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
    await asyncio.sleep(4)
    await client_.stop()
    return

async def call_flow(_call):
    stream = await _call.call_handler.say("Well today was kind of a beautiful day")
    await stream.wait_finished()
    await _call.call_handler.transfer_to(3001)
    await _call.call_handler.hangup()
    await client.stop()


async def main():
    asyncio.get_event_loop().set_debug(True)
    client_task = asyncio.create_task(client.run())
    
    call_task = asyncio.create_task(call.start())
 
    await asyncio.gather(client_task, call_task, call_flow(call), return_exceptions=False
                         )
    call.get_recorded_audio(f'call_{str(uuid.uuid4())}.wav')

async def main_new():
    asyncio.get_event_loop().set_debug(True)
    client_task = asyncio.create_task(client.run())

    calls = []
    call_tasks = []
    call_handlers = []
    for i in range(10):
        c = '111' if i == 5 else '112'
        print(c)
        call = SipCall('3001', '30013001', '192.168.1.112:5060', c)
        calls.append(call)

        call_task = asyncio.create_task(call.start())
        call_tasks.append(call_task)

        call_handler_task = asyncio.create_task(call_flow(call))
        call_handlers.append(call_handler_task)

    await asyncio.gather(client_task, *call_tasks, *call_handlers)

    for c in calls:
        c.get_recorded_audio(f"call_{c.call_id}")


# Protect the entery-point because we use ProcessPoolExecutor
if __name__ == "__main__":
    asyncio.run(main_new())
