

import asyncio
from PySIP.sip_account import SipAccount

account = SipAccount('3001', '30013001', '192.168.1.112:5060')

call = account.make_call('111')
print(call)


async def main():
    # await account.register()
    
    # call = account.make_call('111')
    call_task = asyncio.create_task(call.start())

    try:
        await call.call_handler.say("Welcome to PayPal fraud prevention line")
        await call.call_handler.say("We have recently received an online purchase request if this was not you presee 1")
        dtmf_key = await call.call_handler.gather()
        print(dtmf_key)
    except RuntimeError:
        print("Call is no longer running")

    await call_task


if __name__ == "__main__":
    asyncio.run(main())
    # loop.run_until_complete(asyncio.sleep(2))
    # account.unregister_sync()
    # loop.close()
