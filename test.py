import asyncio
from PySIP.sip_account import SipAccount
from scripts.appointment_booking_bot import appointment_booking_bot

# account = SipAccount('michel2', 'pass1234', '109.207.170.23:5060', connection_type='UDP', caller_id='18006566561')
account = SipAccount(
    "12035473096",
    "etAywogjnDHPUbfoUY2tovgQ2ekZZM93/LBeO1B9dbGTt7pCXLG7esa8A5pa5/8DY2dDH2LXtKsIyc1pE1YfuA==",
    "talk.waafi.com:2382",
    connection_type="TLSv1",
)

# call = account.make_call('12045148765')
# print(call)


async def main():
    await account.register()

    call = account.make_call("33650691262")
    call_task = asyncio.create_task(call.start())

    await appointment_booking_bot(call.call_handler, customer_name="Muna")

    await call_task
    call.get_recorded_audio()
    await account.unregister()


if __name__ == "__main__":
    asyncio.run(main())
    # loop.run_until_complete(asyncio.sleep(2))
    # account.unregister_sync()
    # loop.close()
