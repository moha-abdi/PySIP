# PySIP: Making VoIP Calls with Python

PySIP is an open-source Python library for making VoIP calls using the SIP (Session Initiation Protocol) and SDP (Session Description Protocol).

## Features

- Make VoIP calls with SIP
- Use SDP for session negotiation
- Asynchronous API for real-time performance

## Installation

Currently I didn't add pip installation for
version `v1.0.0` so clone the repository instead:

```bash
git clone https://github.com/pysip/pysip.git
```
## Usage

### Making a Call

```python
from pysip import VOIP

voip = VOIP('username', 'server:port', 'password')

text = "Hello, this is a test call"

voip.call('destination_number', tts=True, text=text)
```
### SIP Message Filters

PySIP provides filters for handling specific SIP messages:

```python
from pysip.filters import SipFilter

@voip.client.on_message(filters=SipFilter.INVITE)
def handle_invite(msg):
    print('Received invite:', msg)

@voip.client.on_message(filters=SipFilter.OK)
def handle_ok(msg):
    print('Received OK:', msg)
```
### Audio Handling

You can provide audio files or generate TTS audio for the call:

```python
from pysip import TTS

tts = TTS('Hello, this is a test call', 'voice')
audio_file = await tts.generate_audio()

voip.call('number', audio_file=audio_file)
```
Or call using TTS (Auto geerated audio from text input)
```python
text = "Hello, this is a call for Moha"
voip.call('number', audio_file=audio_file)
```
## Documentation

Detailed documentation and usage examples are coming soon. Please stay tuned!

## Contributing

Contributions are welcome! Will add more details soon.

## License

This project is licensed under the [MIT License](LICENSE).


