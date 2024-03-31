

import asyncio
from PySIP.sip_account import SipAccount

loop = asyncio.new_event_loop()
account = SipAccount('3001', '30013001', '192.168.1.112:5060', loop=loop)
account.register_sync()

call = account.make_call('111')
print(call)

async def main():
    await account.register()
    
    call = account.make_call('111')
    call_task = asyncio.create_task(call.start())

    await call.call_handler.say("hello folk i hope good for you ")

    await call_task


if __name__ == "__main__":
    # asyncio.run(main())
    loop.run_until_complete(asyncio.sleep(2))
    account.unregister_sync()
    loop.close()
