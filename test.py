from PySIP.call import VOIP
from PySIP.call_handler import CallHandler
import asyncio


voip = VOIP(
    "12098768975",
    "server:port",
    connection_type="UDP",
    password="your_password",
)
call_handler = CallHandler(voip)


async def call_flow() -> None:
    await call_handler.say("Hello and welcome to PySIP")
    await call_handler.say("How are you doing today")
    await call_handler.say("Please type 55 to continue this call")

    dtmf_result_found = False
    for _ in range(3):
        try:
            dtmf_result = await call_handler.gather(length=2, timeout=5.0)

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


async def main():
    # Run the voip.call asynchronously
    call_task = asyncio.create_task(voip.call("13209876534"))

    # Concurrently run other tasks
    other_tasks = [
        asyncio.create_task(call_flow()),
        asyncio.create_task(call_handler.send_handler()),
    ]

    # Wait for all tasks to complete
    await asyncio.gather(call_task, *other_tasks)

    if voip.received_bytes:
        print("Recorded audio saved to recored.mp3")


asyncio.run(main())
