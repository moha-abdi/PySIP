import asyncio
import os
from PySIP.sip_account import SipAccount
from scripts.appointment_booking_bot import appointment_booking_bot
from dotenv import load_dotenv

load_dotenv()

account = SipAccount(
    os.environ["SIP_USERNAME"],
    os.environ["SIP_PASSWORD"],
    os.environ["SIP_SERVER"],
)


async def main():
    await account.register()

    call = account.make_call("111")
    call_task = asyncio.create_task(call.start())

    await appointment_booking_bot(call.call_handler, customer_name="John")

    await call_task
    await account.unregister()


if __name__ == "__main__":
    asyncio.run(main())
    # loop.run_until_complete(asyncio.sleep(2))
    # account.unregister_sync()
    # loop.close()
