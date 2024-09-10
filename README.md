<p align="center">
  <img src=".github/images/banner.png" alt="PySIP Logo" style="display: block; margin: 0 auto;">
</p>
<p align="center">
  <b>Python SIP Library for Custom VoIP Solutions</b>
</p>

**PySIP** is an asynchronous Python library designed to simplify working with the Session Initiation Protocol (SIP) for VoIP communication. Whether you're building automated call systems, interactive voice response (IVR) menus, or any SIP-based application, PySIP gives you the flexibility to create and manage SIP accounts, handle calls, and implement custom logic with ease.

## ✨ **Features**

<table style="width: 100%; border-collapse: separate; border-spacing: 0 10px;">
  <tr>
    <th style="text-align: left; padding: 10px 0;">Feature</th>
    <th style="text-align: left; padding: 10px 0;">Description</th>
  </tr>
  <tr>
    <td style="padding: 10px; background-color: #f6f8fa; font-weight: bold;">
      Complete SIP Account Management
    </td>
    <td style="padding: 10px; background-color: #f6f8fa; border-radius: 0 6px 6px 0;">
      Easily create, register, and manage SIP accounts.
    </td>
  </tr>
  <tr>
    <td style="padding: 10px; background-color: #f6f8fa; font-weight: bold;">
      Custom Call Flows
    </td>
    <td style="padding: 10px; background-color: #f6f8fa; border-radius: 0 6px 6px 0;">
      Write scripts to automate call flows with your own business logic.
    </td>
  </tr>
  <tr>
    <td style="padding: 10px; background-color: #f6f8fa; font-weight: bold;">
      UDP Transport Layer
    </td>
    <td style="padding: 10px; background-color: #f6f8fa; border-radius: 0 6px 6px 0;">
      Asynchronous, efficient UDP transport for sending and receiving SIP messages.
    </td>
  </tr>
  <tr>
    <td style="padding: 10px; background-color: #f6f8fa; font-weight: bold;">
      Flexible Call Handling
    </td>
    <td style="padding: 10px; background-color: #f6f8fa; border-radius: 0 6px 6px 0;">
      Handle incoming and outgoing SIP calls, play messages, and gather user input.
    </td>
  </tr>
  <tr>
    <td style="padding: 10px; background-color: #f6f8fa; font-weight: bold;">
      Fully Extensible
    </td>
    <td style="padding: 10px; background-color: #f6f8fa; border-radius: 0 6px 6px 0;">
      Includes an example bot for appointment booking, but you can easily write any SIP-based automation you need.
    </td>
  </tr>
</table>


## 📚 **Table of Contents**
1. [Installation](#-installation)
2. [Project Structure](#-project-structure)
3. [Getting Started](#-getting-started)
4. [Detailed Usage](#-detailed-usage)
   - [SIP Account](#sip-account)
   - [Call Handling](#call-handling)
   - [UDP Transport](#udp-transport)
5. [Example Script](#-example-script)
6. [Creating Your Custom SIP Scripts](#-creating-your-custom-sip-scripts)
7. [Contributing](#-contributing)

---

## 🚀 **Installation**

<div style="background-color: #f6f8fa; border-radius: 6px; padding: 16px;">

### Step 1: Clone the repository
```bash
git clone https://github.com/moha-abdi/PySIP.git
cd PySIP
```

### Step 2: Install dependencies
Ensure you have Python 3.8+ installed. Install the required dependencies using:
```bash
pip install -r requirements.txt
```

### Step 3: Environment Setup
Create a `.env` file to store your SIP account credentials and server details:
```bash
SIP_USERNAME=your_sip_username
SIP_PASSWORD=your_sip_password
SIP_SERVER=your_sip_server
```
</div>

---

## 📁 **Project Structure**

The project is structured to provide a clean separation between the core SIP library and any custom scripts you want to write. Here's an overview of the project layout:

<div style="background-color: #f6f8fa; border-radius: 6px; padding: 16px;">

```
PySIP/
│
├── PySIP/                     # Core library files
│   ├── sip_account.py          # SIP account management
│   ├── sip_core.py             # SIP message parsing and handling
│   ├── udp_handler.py          # Asynchronous UDP transport for SIP
│
├── scripts/                    # Example custom scripts
│   └── appointment_booking_bot.py  # Example bot for appointment booking
│
├── test.py                     # Example usage of PySIP for testing
├── requirements.txt            # Project dependencies
├── .env.example                # Example environment configuration
└── README.md                   # Project documentation
```
</div>

---

## 🏁 **Getting Started**

<div style="background-color: #f6f8fa; border-radius: 6px; padding: 16px;">

### Step 1: Setting Up a SIP Account
A SIP account is essential for handling calls. To start, you need to create an instance of the `SipAccount` class, which requires your SIP credentials (username, password, and server). Here's how to do it:

```python
from PySIP.sip_account import SipAccount
import os
from dotenv import load_dotenv

# Load SIP credentials from .env file
load_dotenv()

account = SipAccount(
    os.environ["SIP_USERNAME"],
    os.environ["SIP_PASSWORD"],
    os.environ["SIP_SERVER"],
)
```

### Step 2: Registering the Account
Once the `SipAccount` is created, the next step is to register it with the SIP server:
```python
await account.register()
```
This sends a SIP `REGISTER` request to the server to activate the account. Once registered, you can make calls or listen for incoming calls.
</div>

---

## 📘 **Detailed Usage**

### SIP Account

<div style="background-color: #f6f8fa; border-radius: 6px; padding: 16px;">

The `SipAccount` class is at the core of PySIP. It handles all account-related tasks such as registration, making calls, and unregistering from the SIP server.

#### **Instantiating a SIP Account**:
```python
account = SipAccount(username, password, server)
```

#### **Registering**:
Call the `register()` method to register the SIP account with the server:
```python
await account.register()
```

#### **Making Calls**:
The `make_call(destination)` method initiates a call to the destination number:
```python
call = account.make_call("destination_number")
```

#### **Unregistering**:
When you're done, unregister the account to gracefully close the session:
```python
await account.unregister()
```
</div>

### Call Handling

<div style="background-color: #f6f8fa; border-radius: 6px; padding: 16px;">

The `CallHandler` is responsible for handling the call flow. It allows you to say messages, gather input from the caller, or transfer the call.

#### **Playing a message to the caller**:
```python
await call_handler.say("Welcome to our service.")
```

#### **Gathering user input**:
Use `gather()` to gather input from the user, such as pressing a digit:
```python
dtmf_key = await call_handler.gather(length=1, timeout=5)
```

#### **Transferring the call**:
You can forward the call to another number:
```python
await call_handler.transfer_to("1234567890")
```
</div>

### UDP Transport

<div style="background-color: #f6f8fa; border-radius: 6px; padding: 16px;">

The `UdpHandler` is an internal module that manages the asynchronous sending and receiving of SIP messages over the network.

#### **Sending a message**:
The `send_message()` method sends a UDP message to the SIP server or peer:
```python
self.transport.sendto(message)
```

#### **Receiving a datagram**:
The `datagram_received()` method handles incoming messages, placing them in a queue for processing:
```python
self.data_q.put_nowait(data)
```
</div>

---

## 🔍 **Example Script**

To demonstrate PySIP in action, we've provided a basic example of an appointment booking bot. This bot allows callers to book appointments via a phone call.

<div style="background-color: #f6f8fa; border-radius: 6px; padding: 16px;">

```python
import asyncio
from PySIP.sip_account import SipAccount
from scripts.appointment_booking_bot import appointment_booking_bot
from dotenv import load_dotenv
import os

# Load environment variables
load_dotenv()

# Initialize SIP account with credentials from .env file
account = SipAccount(
    os.environ["SIP_USERNAME"],
    os.environ["SIP_PASSWORD"],
    os.environ["SIP_SERVER"],
)

async def main():
    # Register the SIP account
    await account.register()

    # Make a call to a test number (e.g., '111')
    call = account.make_call("111")
    call_task = asyncio.create_task(call.start())

    # Run the appointment booking bot
    await appointment_booking_bot(call.call_handler, customer_name="John")

    # Wait for the call to complete, then unregister
    await call_task
    await account.unregister()

if __name__ == "__main__":
    asyncio.run(main())
```
</div>

---

## 🛠 **Creating Your Custom SIP Scripts**

While the appointment booking bot is just one example, **PySIP** is designed to let you create any SIP-based automation or custom script that fits your needs.

To create your own script:
1. **Create a Python file** in the `scripts/` directory.
2. **Write your custom call logic** using the `CallHandler` class to control the call flow.
3. **Use the `SipAccount` to register and make calls** as demonstrated in the example script.

---

## 🤝 **Contributing**

Contributions are welcome! If you would like to contribute to the development of PySIP, feel free to open issues or submit pull requests.

---

<div style="text-align: center; align: center; margin-top: 30px;" align="center">
  <p align="center">Made with ❤️ by the Moha Abdi</p>
</div>
