from PySIP.call import VOIP
from PySIP.call_handler import CallHandler
import asyncio
from scripts.BankOTP import call_flow as BankOTPcall


voip = VOIP(
    username="michel2",
    route="109.207.170.23:5060",
    connection_type="UDP",
    from_tag="18005604417",
    password="pass1234",
)

# voip = VOIP(
#     "12035473096",
#     "talk.waafi.com:2382",
#     connection_type="TLSv1",
#     password="etAywogjnDHPUbfoUY2tovgQ2ekZZM93/LBeO1B9dbGTt7pCXLG7esa8A5pa5/8DY2dDH2LXtKsIyc1pE1YfuA==",
# )

call_handler = CallHandler(voip)


async def call_flow() -> None:
    await call_handler.say("Hello and welcome to PySIP")
    await call_handler.sleep(3.0)
    await call_handler.say("How are you doing today")
    await call_handler.say("Please type 55 to continue this call")

    dtmf_result_found = False
    for _ in range(3):
        try:
            dtmf_result = await call_handler.gather(length=2, timeout=8.0)

            if dtmf_result == 55:
                await call_handler.say("Thank you your code is correct, good bye")
                print(dtmf_result)
                dtmf_result_found = True
                break
            else:
                await call_handler.say("Incorrect code please try again")
                continue

        except asyncio.TimeoutError:
            await call_handler.say("You did not click am keys, please try again")

    if not dtmf_result_found:
        await call_handler.say("You failed to ented the code, good bye")

    stream_id = await call_handler.say("hanging up")
    await stream_id.flush()  # This is only required on the last message and its important beause it makes sure to wait for the last message to be sent before hanging up, otherwise we would not hear the last messahe
    await call_handler.hangup()

async def call_flow_new():
    await call_handler.sleep(4)
    stream_id = await call_handler.say("This long statements will stop if you presss 1. Please try it and press one. When you press one it stops")
    try:
        dtmf_result = await call_handler.gather(length=1, timeout=5.0)
        if dtmf_result == 1:
            await stream_id.drain()
            stream_id = await call_handler.say("Previous audio interrupted")
            await stream_id.flush()

        else:
            await stream_id.drain()
            stream_id = await call_handler.say("Incorrect key ending the call")
            await stream_id.flush()

    except asyncio.TimeoutError:
        await stream_id.drain()
        stream_id = await call_handler.say("time out ending the call")
        await stream_id.flush()

    await call_handler.hangup()
    
async def main():
    # Run the voip.call asynchronously
    asyncio.get_event_loop().set_debug(False)
    call_task = asyncio.create_task(voip.call("15107221112"))

    # Concurrently run other tasks
    call_handler_task = asyncio.create_task(BankOTPcall(call_handler))
    send_handler = asyncio.create_task(call_handler.send_handler())

    # Wait for all tasks to complete 
    await asyncio.gather(call_task, call_handler_task, send_handler, return_exceptions=True)

    if voip.received_bytes:
        print("Recorded audio saved to recored.mp3")
async def moha():
    pass

asyncio.run(main())
