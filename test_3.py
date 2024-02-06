import asyncio
from enum import Enum


async def loop_task(event: asyncio.Event):
    await asyncio.sleep(0.1)
    while True:
        if not event.is_set():
            print("Loop finished for event is no longer set")
            break

        await asyncio.sleep(0.1)


async def event_setter(event: asyncio.Event):
    event.set()
    await asyncio.sleep(4)
    event.clear()
    print("event is no longer set: ", event.is_set())


async def main():
    event = asyncio.Event()

    await asyncio.gather(loop_task(event), event_setter(event))


# asyncio.run(main())
print("O" or 5)

ls = None
m = None

print(any([ls, m]))

to = "sip:michel2@41.79.197.220:59443;transport=UDP;rinstance=04ebcf29d80de0d0>"
uri = to.split(";", 1)[0] + ">" if ";" in to else to
uri = "<" + uri if not uri.startswith("<") else uri
print(uri)



class Counter:
    def __init__(self, start: int = 1):
        self.x = start

    def count(self) -> int:
        x = self.x
        self.x += 1
        return x

    def next(self) -> int:
        return self.count()

    def current(self) -> int:
        return self.x


class Counter:
  def __init__(self, start: int = 1):
    self.x = start 

  def current(self) -> int:
    return self.x

  def __iter__(self):
    return self

  def __next__(self):
    self.x += 1
    return self.x
c = Counter(1)
print(next(c))
print(c.current())
print(next(c))


class SIPStatus(Enum):
    def __new__(cls, value: int, phrase: str = "", description: str = ""):
        obj = object.__new__(cls)

        obj._value_ = value
        obj.phrase = phrase
        obj.description = description

        return obj

    def __str__(self) -> str:
        return f"{self._value_} {self.phrase}"

    def __int__(self) -> int:
        return self._value_

    @property
    def code(self) -> int:
        return self._value_

    @property
    def description(self):
        return self._description

    @description.setter
    def description(self, description):
        self._description = description

    @property
    def phrase(self):
        return self._phrase

    @phrase.setter
    def phrase(self, value):
        self._phrase = value

    # Informational
    TRYING = (
        100,
        "Trying",
        "Extended search being performed, may take a significant time",
    )
    RINGING = (
        180,
        "Ringing",
        "Destination user agent received INVITE, "
        + "and is alerting user of call",
    )

print(SIPStatus(100) == 100)


import asyncio
from enum import Enum, auto

class DialogState(Enum):
    INITIAL = auto()
    EARLY = auto()
    CONFIRMED = auto()
    TERMINATED = auto()

class Dialog:
    def __init__(self):
        self.state = DialogState.INITIAL
        self.events = {state: asyncio.Event() for state in DialogState}

    async def wait_for_state(self, state):
        await self.events[state].wait()

    async def simulate_processing(self):
        await asyncio.sleep(2)
        self.state = DialogState.INITIAL
        self.events[DialogState.INITIAL].set()
        await asyncio.sleep(2)
        self.state = DialogState.EARLY
        self.events[DialogState.EARLY].set()
        print('set it now again')
        self.events[DialogState.EARLY].set()
        print('test passed')
        await asyncio.sleep(2)
        self.state = DialogState.CONFIRMED
        self.events[DialogState.CONFIRMED].set()
        await asyncio.sleep(2)
        self.state = DialogState.TERMINATED
        self.events[DialogState.TERMINATED].set()

async def main():
    dialog = Dialog()
    await asyncio.gather(
        dialog.events[DialogState.INITIAL].wait(),
        dialog.events[DialogState.EARLY].wait(),
        dialog.events[DialogState.CONFIRMED].wait(),
        dialog.events[DialogState.TERMINATED].wait(),
        dialog.simulate_processing()
    )
