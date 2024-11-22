import asyncio
import os
from PySIP.call_handler import CallHandler

# Set the base directory for resources
BASE_DIR = os.path.join(os.path.dirname(__file__), "resources")


async def smart_thermostat_setup_bot(call_handler: CallHandler, customer_name: str):
    try:
        call_handler.voice = "fr-FR-DeniseNeural"

        # Step 1: Greeting and Heating Type
        await call_handler.play(os.path.join(BASE_DIR, "step1.mp3"), format="mp3")

        heating_type = await call_handler.gather_and_play(
            format="mp3",
            length=1,
            delay=5,
            delay_audio_file=os.path.join(BASE_DIR, "invalid_choice.mp3"),
            loop_audio_file=os.path.join(BASE_DIR, "invalid_choice.mp3"),
        )

        if heating_type == "1" or heating_type == "2":
            print("User has selected heating type:", heating_type)
            pass
        else:
            await call_handler.play(os.path.join(BASE_DIR, "invalid_choice.mp3"))
            await call_handler.hangup()
            return

        await asyncio.sleep(0.5)

        # Step 2: Gather Number of Radiators
        await call_handler.play(os.path.join(BASE_DIR, "step2.mp3"), format="mp3")
        radiator_count = await call_handler.gather_and_play(
            format="mp3",
            length=2,
            delay=10,
            finish_on_key="#",
            delay_audio_file=os.path.join(BASE_DIR, "invalid_choice.mp3"),
            loop_audio_file=os.path.join(BASE_DIR, "invalid_choice.mp3"),
        )

        if radiator_count:
            print("Customer has entered radiator count of:", radiator_count)
        else:
            await call_handler.play(
                os.path.join(BASE_DIR, "invalid_choice.mp3"), format="mp3"
            )
            await call_handler.hangup()
            return

        await asyncio.sleep(1)

        # Step 3: Preferred Callback Time
        await call_handler.play(os.path.join(BASE_DIR, "step3.mp3"), format="mp3")
        callback_time = await call_handler.gather_and_play(
            format="mp3",
            length=1,
            delay=5,
            delay_audio_file=os.path.join(BASE_DIR, "invalid_choice.mp3"),
            loop_audio_file=os.path.join(BASE_DIR, "invalid_choice.mp3"),
        )

        if callback_time in ["1", "2", "3"]:
            print("Customer has chosen callback time option:", callback_time)
        else:
            await call_handler.play(
                os.path.join(BASE_DIR, "invalid_choice.mp3"), format="mp3"
            )
            await call_handler.hangup()
            return

        # Final Confirmation
        stream = await call_handler.play(
            os.path.join(BASE_DIR, "end_message.mp3"), format="mp3"
        )
        await stream.wait_finished()
        await call_handler.hangup()

    except RuntimeError:
        print("Error occurred stopping the bot...")
