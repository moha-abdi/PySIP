from enum import IntEnum, Enum
import random
import re
from typing import Any, Literal, Union

__all__ = [
    'SIPCompatibleMethods',
    'SIPCompatibleVersions',
    'SIPMessageType',
    'Filter',
    'MethodFilter',
    'TypeFilter',
    'SipFilter',
    'SIPStatus', 
    'PayloadType'
]

SIPCompatibleMethods = ["INVITE", "ACK", "BYE", "CANCEL", "UPDATE",
                        "INFO", "SUBSCRIBE", "NOTIFY", "REFER", "MESSAGE", "OPTIONS"]
SIPCompatibleVersions = ["SIP/2.0"]

class SIPMessageType(IntEnum):
    def __new__(cls, value: int):
        obj = int.__new__(cls, value)
        obj._value_ = value
        return obj

    MESSAGE = 1
    RESPONSE = 0


class ConnectionType(Enum):
    TCP = 'TCP'
    UDP = 'UDP'
    TLS = 'TLS'
    TLSv1 = 'TLSv1'


class CallState(Enum):
    INITIALIZING = "INITIALIZING"
    DAILING = "DIALING"
    RINGING = "RINGING"
    ANSWERED = "ANSWERED"
    ENDED = "ENDED"
    FAILED = "FAILED"
    BUSY = "BUSY"


class Filter:
    def __init__(self):
        self.conditions = [self]

    def __or__(self, other):
        new_filter = Filter()
        new_filter.conditions = self.conditions + ["or"] + other.conditions
        return new_filter

    def __and__(self, other):
        new_filter = Filter()
        new_filter.conditions = self.conditions + ["and"] + other.conditions
        return new_filter

class MethodFilter(Filter):
    def __init__(self, method):
        super().__init__()
        self.method = method

    def __call__(self, msg) -> bool:
        return msg.method == self.method

class TypeFilter(Filter):
    def __init__(self, type_):
        super().__init__()
        self.type_ = type_

    def __call__(self, msg) -> Any:
        return msg.type == self.type_

class CallIdFilter(Filter):
    def __init__(self, call_id):
        super().__init__()
        self.call_id = call_id

    def __call__(self, msg):
        return msg.call_id == self.call_id

class SipFilter:
    """Filter received :obj:`SipMessage``s"""

    INVITE: 'SipFilter' = MethodFilter('INVITE')
    """This puts a filter that only filters the
    :attr:`SipMessage.method` which returns Invite."""
    REGISTER: 'SipFilter' = MethodFilter('REGISTER')
    """This puts a filter that only filters the
    :attr:`SipMessage.method` which returns Register."""
    REINVITE: 'SipFilter' = MethodFilter('REINVITE')
    """This puts a filter that only filters the
    :attr:`SipMessage.method` which returns Re-invite."""
    REREGISTER: 'SipFilter' = MethodFilter('REREGISTER')
    """This puts a filter that only filters the
    :attr:`SipMessage.method` which returns Re-register."""
    ACK: 'SipFilter' = MethodFilter('ACK')
    """This puts a filter that only filters the
    :attr:`SipMessage.method` which returns Ack."""
    REFER: 'SipFilter' = MethodFilter('REFER')
    """This puts a filter that only filters the
    :attr:`SipMessage.method` which returns Refer."""
    NOTIFY: 'SipFilter' = MethodFilter('NOTIFY')
    """This puts a filter that only filters the
    :attr:`SipMessage.method` which returns Notify."""
    OK: 'SipFilter' = MethodFilter('OK')
    """This puts a filter that only filters the
    :attr:`SipMessage.method` which returns Ok."""
    OPTIONS: 'SipFilter' = MethodFilter('OPTIONS')
    """This puts a filter that only filters the
    :attr:`SipMessage.method` which returns Options."""
    BYE: 'SipFilter' = MethodFilter('BYE')
    """This puts a filter that only filters the
    :attr:`SipMessage.method` which returns Bye."""
    CANCEL: 'SipFilter' = MethodFilter('CANCEL')
    """This puts a filter that only filters the
    :attr:`SipMessage.method` which returns Cancel."""
    RESPONSE: 'SipFilter' = TypeFilter(SIPMessageType.RESPONSE)
    """This filters out only the messages that are from the server.
    from :meth:`Client.receive`"""
    REQUEST: 'SipFilter' = TypeFilter(SIPMessageType.MESSAGE)
    """This filters out only the messages that are sent out to
    the server through :meth:`Client.send`"""
    CALL_ID: 'SipFilter' = lambda callid: CallIdFilter(callid)


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
    FORWARDED = 181, "Call is Being Forwarded"
    QUEUED = 182, "Queued"
    SESSION_PROGRESS = 183, "Session Progress"
    TERMINATED = 199, "Early Dialog Terminated"

    # Success
    OK = 200, "OK", "Request successful"
    ACCEPTED = (
        202,
        "Accepted",
        "Request accepted, processing continues (Deprecated.)",
    )
    NO_NOTIFICATION = (
        204,
        "No Notification",
        "Request fulfilled, nothing follows",
    )

    # Redirection
    MULTIPLE_CHOICES = (
        300,
        "Multiple Choices",
        "Object has several resources -- see URI list",
    )
    MOVED_PERMANENTLY = (
        301,
        "Moved Permanently",
        "Object moved permanently -- see URI list",
    )
    MOVED_TEMPORARILY = (
        302,
        "Moved Temporarily",
        "Object moved temporarily -- see URI list",
    )
    USE_PROXY = (
        305,
        "Use Proxy",
        "You must use proxy specified in Location to "
        + "access this resource",
    )
    ALTERNATE_SERVICE = (
        380,
        "Alternate Service",
        "The call failed, but alternatives are available -- see URI list",
    )

    # Client Error
    BAD_REQUEST = (
        400,
        "Bad Request",
        "Bad request syntax or unsupported method",
    )
    UNAUTHORIZED = (
        401,
        "Unauthorized",
        "No permission -- see authorization schemes",
    )
    PAYMENT_REQUIRED = (
        402,
        "Payment Required",
        "No payment -- see charging schemes",
    )
    FORBIDDEN = (
        403,
        "Forbidden/Invalid",
        "Request forbidden -- authorization will not help",
    )
    NOT_FOUND = (404, "Not Found", "Nothing matches the given URI")
    METHOD_NOT_ALLOWED = (
        405,
        "Method Not Allowed",
        "Specified method is invalid for this resource",
    )
    NOT_ACCEPTABLE = (
        406,
        "Not Acceptable",
        "URI not available in preferred format",
    )
    PROXY_AUTHENTICATION_REQUIRED = (
        407,
        "Proxy Authentication Required",
        "You must authenticate with this proxy before proceeding",
    )
    REQUEST_TIMEOUT = (
        408,
        "Request Timeout",
        "Request timed out; try again later",
    )
    CONFLICT = 409, "Conflict", "Request conflict"
    GONE = (
        410,
        "Gone",
        "URI no longer exists and has been permanently removed",
    )
    LENGTH_REQUIRED = (
        411,
        "Length Required",
        "Client must specify Content-Length",
    )
    CONDITIONAL_REQUEST_FAILED = 412, "Conditional Request Failed"
    REQUEST_ENTITY_TOO_LARGE = (
        413,
        "Request Entity Too Large",
        "Entity is too large",
    )
    REQUEST_URI_TOO_LONG = 414, "Request-URI Too Long", "URI is too long"
    UNSUPPORTED_MEDIA_TYPE = (
        415,
        "Unsupported Media Type",
        "Entity body in unsupported format",
    )
    UNSUPPORTED_URI_SCHEME = (
        416,
        "Unsupported URI Scheme",
        "Cannot satisfy request",
    )
    UNKOWN_RESOURCE_PRIORITY = (
        417,
        "Unkown Resource-Priority",
        "There was a resource-priority option tag, "
        + "but no Resource-Priority header",
    )
    BAD_EXTENSION = (
        420,
        "Bad Extension",
        "Bad SIP Protocol Extension used, not understood by the server.",
    )
    EXTENSION_REQUIRED = (
        421,
        "Extension Required",
        "Server requeires a specific extension to be "
        + "listed in the Supported header.",
    )
    SESSION_INTERVAL_TOO_SMALL = 422, "Session Interval Too Small"
    SESSION_INTERVAL_TOO_BRIEF = 423, "Session Interval Too Breif"
    BAD_LOCATION_INFORMATION = 424, "Bad Location Information"
    USE_IDENTITY_HEADER = (
        428,
        "Use Identity Header",
        "The server requires an Identity header, "
        + "and one has not been provided.",
    )
    PROVIDE_REFERRER_IDENTITY = 429, "Provide Referrer Identity"
    """
    This response is intended for use between proxy devices,
    and should not be seen by an endpoint. If it is seen by one,
    it should be treated as a 400 Bad Request response.
    """
    FLOW_FAILED = (
        430,
        "Flow Failed",
        "A specific flow to a user agent has failed, "
        + "although other flows may succeed.",
    )
    ANONYMITY_DISALLOWED = 433, "Anonymity Disallowed"
    BAD_IDENTITY_INFO = 436, "Bad Identity-Info"
    UNSUPPORTED_CERTIFICATE = 437, "Unsupported Certificate"
    INVALID_IDENTITY_HEADER = 438, "Invalid Identity Header"
    FIRST_HOP_LACKS_OUTBOUND_SUPPORT = 439, "First Hop Lacks Outbound Support"
    MAX_BREADTH_EXCEEDED = 440, "Max-Breadth Exceeded"
    BAD_INFO_PACKAGE = 469, "Bad Info Package"
    CONSENT_NEEDED = 470, "Consent Needed"
    TEMPORARILY_UNAVAILABLE = 480, "Temporarily Unavailable"
    CALL_OR_TRANSACTION_DOESNT_EXIST = 481, "Call/Transaction Does Not Exist"
    LOOP_DETECTED = 482, "Loop Detected"
    TOO_MANY_HOPS = 483, "Too Many Hops"
    ADDRESS_INCOMPLETE = 484, "Address Incomplete"
    AMBIGUOUS = 485, "Ambiguous"
    BUSY_HERE = 486, "Busy Here", "Callee is busy"
    REQUEST_TERMINATED = 487, "Request Terminated"
    NOT_ACCEPTABLE_HERE = 488, "Not Acceptable Here"
    BAD_EVENT = 489, "Bad Event"
    REQUEST_PENDING = 491, "Request Pending"
    UNDECIPHERABLE = 493, "Undecipherable"
    SECURITY_AGREEMENT_REQUIRED = 494, "Security Agreement Required"

    # Server Errors
    INTERNAL_SERVER_ERROR = (
        500,
        "Internal Server Error",
        "Server got itself in trouble",
    )
    NOT_IMPLEMENTED = (
        501,
        "Not Implemented",
        "Server does not support this operation",
    )
    BAD_GATEWAY = (
        502,
        "Bad Gateway",
        "Invalid responses from another server/proxy",
    )
    SERVICE_UNAVAILABLE = (
        503,
        "Service Unavailable",
        "The server cannot process the request due to a high load",
    )
    GATEWAY_TIMEOUT = (
        504,
        "Server Timeout",
        "The server did not receive a timely response",
    )
    SIP_VERSION_NOT_SUPPORTED = (
        505,
        "SIP Version Not Supported",
        "Cannot fulfill request",
    )
    MESSAGE_TOO_LONG = 513, "Message Too Long"
    PUSH_NOTIFICATION_SERVICE_NOT_SUPPORTED = (
        555,
        "Push Notification Service Not Supported",
    )
    PRECONDITION_FAILURE = 580, "Precondition Failure"

    # Global Failure Responses
    BUSY_EVERYWHERE = 600, "Busy Everywhere"
    DECLINE = 603, "Decline"
    DOES_NOT_EXIST_ANYWHERE = 604, "Does Not Exist Anywhere"
    GLOBAL_NOT_ACCEPTABLE = 606, "Not Acceptable"
    UNWANTED = 607, "Unwanted"
    REJECTED = 608, "Rejected"


class PayloadType(Enum):
    def __new__(
        cls,
        value: Union[int, str],
        clock: int = 0,
        channel: int = 0,
        description: str = "",
    ):
        obj = object.__new__(cls)
        obj._value_ = value
        obj.rate = clock
        obj.channel = channel
        obj.description = description
        return obj

    @property
    def rate(self) -> int:
        return self._rate

    @rate.setter
    def rate(self, value: int) -> None:
        self._rate = value

    @property
    def channel(self) -> int:
        return self._channel

    @channel.setter
    def channel(self, value: int) -> None:
        self._channel = value

    @property
    def description(self) -> str:
        return self._description

    @description.setter
    def description(self, value: str) -> None:
        self._description = value

    def __int__(self) -> int:
        try:
            return int(self.value)
        except ValueError:
            pass
        raise Exception(
            self.description + " is a dynamically assigned payload"
        )

    def __str__(self) -> str:
        if isinstance(self.value, int):
            return self.description
        return str(self.value)

    # Audio
    PCMU = 0, 8000, 1, "PCMU"
    GSM = 3, 8000, 1, "GSM"
    G723 = 4, 8000, 1, "G723"
    DVI4_8000 = 5, 8000, 1, "DVI4"
    DVI4_16000 = 6, 16000, 1, "DVI4"
    LPC = 7, 8000, 1, "LPC"
    PCMA = 8, 8000, 1, "PCMA"
    G722 = 9, 8000, 1, "G722"
    L16_2 = 10, 44100, 2, "L16"
    L16 = 11, 44100, 1, "L16"
    QCELP = 12, 8000, 1, "QCELP"
    CN = 13, 8000, 1, "CN"
    # MPA channel varries, should be defined in the RTP packet.
    MPA = 14, 90000, 0, "MPA"
    G728 = 15, 8000, 1, "G728"
    DVI4_11025 = 16, 11025, 1, "DVI4"
    DVI4_22050 = 17, 22050, 1, "DVI4"
    G729 = 18, 8000, 1, "G729"

    # Video
    CELB = 25, 90000, 0, "CelB"
    JPEG = 26, 90000, 0, "JPEG"
    NV = 28, 90000, 0, "nv"
    H261 = 31, 90000, 0, "H261"
    MPV = 32, 90000, 0, "MPV"
    # MP2T is both audio and video per RFC 3551 July 2003 5.7
    MP2T = 33, 90000, 1, "MP2T"
    H263 = 34, 90000, 0, "H263"

    # Non-codec
    EVENT = 121, 8000, 0, "telephone-event"
    UNKNOWN = "UNKNOWN", 0, 0, "UNKNOWN CODEC"
