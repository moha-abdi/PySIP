import asyncio
from PySIP.call_handler import CallHandler

DELAY_ERR_MESSAGE = (
    "We did not receive any input. Please provide the required information."
)


async def appointment_booking_bot(call_handler: CallHandler, customer_name: str):
    try:
        # Step 1: Greeting
        await call_handler.say(
            f"Hello {customer_name}, thank you for calling. This is the automated booking service for SmallBiz Hair Salon."
        )
        await asyncio.sleep(1)

        # Step 2: Offer service options
        await call_handler.say(
            "Press 1 to book an appointment. Press 2 to speak to a representative. Press 3 to check existing appointments."
        )

        option = await call_handler.gather_and_say(
            length=1, delay=5, delay_msg=DELAY_ERR_MESSAGE
        )

        if option == "1":
            await call_handler.say("You have chosen to book an appointment.")
            await asyncio.sleep(1)

            # Step 3: Gather appointment date
            await call_handler.say(
                "Please enter your preferred appointment date in the format MMDD, followed by the pound key."
            )
            date = await call_handler.gather_and_say(
                length=4, delay=10, finish_on_key="#", delay_msg=DELAY_ERR_MESSAGE
            )

            if date:
                await call_handler.say(f"Your preferred date is {date[:2]}/{date[2:]}.")
            else:
                await call_handler.say(
                    "We did not receive a date. Please try again later. Goodbye."
                )
                await call_handler.hangup()
                return

            # Step 4: Confirm and finalize the appointment
            await call_handler.say(
                "Thank you! We will confirm your appointment shortly. Goodbye."
            )
            await call_handler.hangup()

        elif option == "2":
            await call_handler.say(
                "Please wait while we connect you to a representative."
            )
            await call_handler.transfer_to(
                "+1234567890"
            )  # Forwarding to the business phone number

        elif option == "3":
            await call_handler.say(
                "Please enter your appointment ID followed by the pound key to check your booking."
            )
            appointment_id = await call_handler.gather_and_say(
                length=6, delay=8, finish_on_key="#", delay_msg=DELAY_ERR_MESSAGE
            )

            if appointment_id:
                await call_handler.say(
                    f"Your appointment ID {appointment_id} is confirmed."
                )
            else:
                await call_handler.say(
                    "No appointment ID received. Please try again later. Goodbye."
                )
                await call_handler.hangup()

        else:
            await call_handler.say("Invalid option. Goodbye.")
            await call_handler.hangup()

    except RuntimeError:
        print("The call was disconnected. Stopping the bot...")
