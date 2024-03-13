# PySIP is an open-source Python library designed for making VoIP
# calls using the SIP (Session Initiation Protocol) and
# SDP (Session Description Protocol) protocols.
# It provides asynchronous capabilities, allowing you to create
# VoIP applications that efficiently handle real-time communications.
#
# Key Features:
# - Initiate VoIP calls using the SIP protocol.
# - Utilize SDP for session negotiation and description.
# - Asynchronous design for efficient and non-blocking communications.
#
# Please note that while PySIP provides asynchronous capabilities,
# it may not be fully asynchronous in its current version. However,
# I am actively working to enhance its asynchronous functionality
# and improve overall performance.
#
# For more information and usage examples, visit the
# PySIP GitHub repository: https://github.com/moha-abdi/pysip
import logging
from .utils.logger import logger, console_handler

__version__ = "1.6.0"
__license__ = "MIT License"
__copyright__ = "Copyright (C) 2023-present Moha"


console_handler.setLevel(logging.DEBUG) 
