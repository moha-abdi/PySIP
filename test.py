

import asyncio
from PySIP.sip_account import SipAccount


account = SipAccount('3001', '30013001', '192.168.1.112:5060')

async def main():
    await account.register()
    
    call = await account.make_call('111')
    call_task = asyncio.create_task(call.start())

    await call.call_handler.say("hello folk i hope good for you ")

    await call_task


if __name__ == "__main__":
    asyncio.run(main())
