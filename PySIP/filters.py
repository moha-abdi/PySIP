from enum import IntEnum, Enum
import random
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
    'SipMessage',
    'SDPParser',
    'PayloadType'
]

SIPCompatibleMethods = ["PRACK", "INVITE", "ACK", "BYE", "CANCEL", "UPDATE",
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
    TCP = 1, 'TCP'
    UDP = 2, 'UDP'
    TLS = 3, 'TLS'
    TLSv1 = 4, 'TLSv1'

    def __new__(cls, value: object, conn_type: Literal['TCP', 'UDP', 'TLS', 'TLSv1']):
        obj = object.__new__(cls)
        obj._value_ = value
        obj.conn_type = conn_type
        cls._value2member_map_[conn_type] = obj

        return obj


class CallState(Enum):
    DAILING = "DIALING"
    RINGING = "RINGING"
    ANSWERED = "ANSWERED"
    ENDED = "ENDED"
    FAILED = "FAILED"


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
    OK: 'SipFilter' = MethodFilter('OK')
    """This puts a filter that only filters the
    :attr:`SipMessage.method` which returns Ok."""
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


class SipMessage:
    def __init__(self, message: str = None) -> None:
        self.headers = {}
        self.body = None
        self.nonce = None
        self.realm = None
        self.data = message

        # Initialize properties with default values
        self._type = None
        self._cseq = None
        self._rseq = None
        self._method = None
        self._from_tag = None
        self._to_tag = None
        self._call_id = None
        self._status = None
        self._public_ip = None
        self._rport = None
        self._branch = None
        self._did = None

    @property
    def type(self):
        return self._type

    @type.setter
    def type(self, value):
        self._type = value

    @property
    def cseq(self):
        return self._cseq

    @cseq.setter
    def cseq(self, value):
        self._cseq = value

    @property
    def rseq(self):
        return self._rseq

    @rseq.setter
    def rseq(self, value):
        self._rseq = value

    @property
    def method(self):
        return self._method

    @method.setter
    def method(self, value):
        self._method = value

    @property
    def from_tag(self):
        return self._from_tag

    @from_tag.setter
    def from_tag(self, value):
        self._from_tag = value

    @property
    def to_tag(self):
        return self._to_tag

    @to_tag.setter
    def to_tag(self, value):
        self._to_tag = value

    @property
    def call_id(self):
        return self._call_id

    @call_id.setter
    def call_id(self, value):
        self._call_id = value

    @property
    def status(self):
        return self._status

    @status.setter
    def status(self, value):
        self._status = value

    @property
    def branch(self):
        return self._branch

    @branch.setter
    def branch(self, value):
        self._branch = value

    @property
    def did(self):
        return self._did

    @did.setter
    def did(self, value):
        self._did = value

    @property
    def public_ip(self):
        return self._public_ip

    @public_ip.setter
    def public_ip(self, value):
        self._public_ip = value

    @property
    def rport(self):
        return self._rport

    @rport.setter
    def rport(self, value):
        self._rport = value

    @property
    def nonce(self):
        return self._nonce

    @nonce.setter
    def nonce(self, value):
        self._nonce = value

    @property
    def realm(self):
        return self._realm

    @realm.setter
    def realm(self, value):
        self._realm = value


    def parse(self):
        data = self.data.split('\r\n\r\n')
        self.headers_data = data[0]
        try:
            self.body_data = data[1]
        except IndexError:
            self.body_data = ''

        headers_lines = self.headers_data.split("\r\n")
        for index, line in enumerate(headers_lines):
            if index == 0:  # First line
                self.headers['type'] = line  # Set 'type' in headers

            else:
                key, value = line.split(":", 1)  # Split at first colon
                self.headers[key.strip()] = value.strip()

        if self.body_data != '':
            body_lines = self.body_data.split("\r\n")
            self.body = {}
            for line in body_lines:
                if "=" in line:
                    key, value = line.split("=", 1)
                    if key.strip() in self.body:
                        # This expression checks if the ey value already exists in the
                        # dictionary and if it does then it makes a list of the old value
                        # and the new value, also it checks if it were already a list and just
                        # appends the value t it if it was a list.
                        if not isinstance(self.body[key.strip()], list):
                            self.body[key.strip()] = [self.body[key], value]
                        else:
                            self.body[key.strip()].append(value)
                    else:
                        self.body[key.strip()] = value.strip()

        self.set_properties()

    def set_properties(self):
        """type property, should be LITERAL[Message, Response]"""
        self.type_header = self.get_header('type').split(" ")

        if self.type_header[0] in SIPCompatibleMethods:
            self.type = SIPMessageType.MESSAGE
        elif self.type_header[0] in SIPCompatibleVersions:
            self.type = SIPMessageType.RESPONSE

        """shared properties for both request/response"""
        # CSeq
        cseq = self.get_header('CSeq')
        self.cseq = int(cseq.split(' ')[0])
        self.method = cseq.split(' ')[1]

        from_header = self.get_header('From')
        if ';' in from_header:
            self.from_tag = from_header.split(';')[1].split('=')[1]
        else:
            self.from_tag = None

        to_header = self.get_header('To')
        if ';' in to_header:
            self.to_tag = to_header.split(';')[1].split('=')[1]
        else:
            self.to_tag = None

        self.call_id = self.get_header('Call-ID')

        branch_header = self.get_header('Via')
        self.branch = branch_header.split('branch=')[1].split(";")[0]

        if self.type == SIPMessageType.RESPONSE:
            try:
                self.status = SIPStatus(int(self.type_header[1]))
                via_header = self.get_header('Via')
                self.public_ip = via_header.split('received=')[1].split(";")[0]

                # RPort
                self.rport = via_header.split('rport=')[1].split(';')[0]
                auth_header = self.get_header('WWW-Authenticate')
                if auth_header:
                    self.nonce = auth_header.split('nonce="')[1].split('"')[0]
                    self.realm = auth_header.split('realm="')[1].split('"')[0]
                # dialog_id
                contact_header = self.get_header("Contact")
                if contact_header:
                    try:
                        self.did = contact_header.split("did=")[1].split(">")[0]
                    except IndexError:
                        pass
                #RSeq
                rseq_header = self.get_header("RSeq")
                if rseq_header:
                    self.rseq = rseq_header
            except IndexError:
                pass

    def get_header(self, key) -> str:
        return self.headers.get(key)

    def get_headers(self):
        return self.headers

    def get_body(self, key):
        return self.body.get(key)

    @classmethod
    def generate_sdp(cls, ip):
        ssrc = random.getrandbits(32)
        cname = f"host_{random.randint(100, 999)}"

        sdp = f"v=0\r\n"
        sdp += f"o=- {random.randint(100000000, 999999999)} {random.randint(100000000, 999999999)} IN IP4 {ip}\r\n"
        sdp += f"s=pjmedia\r\n"
        sdp += f"b=AS:84\r\n"
        sdp += f"t=0 0\r\n"
        sdp += f"a=X-nat:1\r\n"
        sdp += f"m=audio 64417 RTP/AVP 96 97 98 99 3 0 8 9 120 121 122\r\n"
        sdp += f"c=IN IP4 {ip}\r\n"
        sdp += f"b=TIAS:64000\r\n"
        sdp += f"a=rtcp:64418 IN IP4 {ip}\r\n"
        sdp += f"a=sendrecv\r\n"
        sdp += cls.get_rtpmap_lines()
        sdp += cls.get_telephone_event_lines()
        sdp += f"a=ssrc:{ssrc} cname:{cname}\r\n"

        return sdp

    @staticmethod
    def get_rtpmap_lines():
        lines = []
        lines.append(f"a=rtpmap:96 speex/16000\r\n")
        lines.append(f"a=rtpmap:97 speex/8000\r\n")
        lines.append(f"a=rtpmap:98 speex/32000\r\n")
        lines.append(f"a=rtpmap:99 iLBC/8000\r\n")
        lines.append(f"a=fmtp:99 mode=30\r\n")
        lines.append(f"a=rtpmap:3 GSM/8000\r\n")
        lines.append(f"a=rtpmap:0 PCMU/8000\r\n")
        lines.append(f"a=rtpmap:8 PCMA/8000\r\n")
        lines.append(f"a=rtpmap:9 G722/8000\r\n")
        return "".join(lines)

    @staticmethod
    def get_telephone_event_lines():
        lines = []
        lines.append(f"a=rtpmap:120 telephone-event/16000\r\n")
        lines.append(f"a=fmtp:120 0-16\r\n")
        lines.append(f"a=rtpmap:121 telephone-event/8000\r\n")
        lines.append(f"a=fmtp:121 0-16\r\n")
        lines.append(f"a=rtpmap:122 telephone-event/32000\r\n")
        lines.append(f"a=fmtp:122 0-16\r\n")
        return "".join(lines)

    @classmethod
    def parse_sdp(cls, sdp):
        parser = SDPParser(sdp)

        return parser

class SDPParser:
    def __init__(self, sdp):
        self.ip_address = None
        self.media_type = None
        self.transport = None
        self.port = None
        self.rtcp_port = None
        self.ptime = None
        self.rtpmap = {}
        self.direction = None

        self.parse_sdp(sdp)

    def parse_sdp(self, sdp):
        self.ip_address = sdp['c'].split(' ')[2]
        m = sdp['m'].split(' ')
        self.media_type = m[0]
        self.transport = m[2]
        self.port = int(m[1])

        for attr in sdp['a']:
            if 'rtcp' in attr:
                self.rtcp_port = int(attr.split(':')[1])
            elif 'ptime' in attr:
                self.ptime = int(attr.split(':')[1])
            elif 'rtpmap' in attr:
                try:
                    rtpmap_val = attr.split(' ')
                    payload_type = int(rtpmap_val[0].split(':')[1])
                    codec = PayloadType(payload_type)
                    self.rtpmap[payload_type] = codec

                except ValueError:
                    continue

            elif 'sendrecv' in attr:
                self.direction = attr

    def __str__(self):
        rtpmap_str = ', '.join([f'{payload_type}: {codec}' for payload_type, codec in self.rtpmap.items()])
        return (
            f"SDP Information:\n"
            f"IP Address: {self.ip_address}\n"
            f"Media Type: {self.media_type}\n"
            f"Transport: {self.transport}\n"
            f"Port: {self.port}\n"
            f"RTCP Port: {self.rtcp_port}\n"
            f"Ptime: {self.ptime}\n"
            f"RTP Map: {rtpmap_str}\n"
            f"Direction: {self.direction}"
        )

    def __repr__(self):
        return str(self)


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
