import logging
from dataclasses import dataclass

from ipv8.messaging.payload_dataclass import DataClassPayload

COMMUNITY_ID_HEX = "2c1cc6e35ff484f99ebdfb6108477783c0102881"
SERVER_PUBLIC_KEY_HEX = (
    "4c69624e61434c504b3a86b23934a28d669c390e2d1fc0b0870706c4591cc0cb"
    "178bc5a811da6d87d27ef319b2638ef60cc8d119724f4c53a1ebfad919c3ac4136c501ce5c09364e0ebb"
)
DIFFICULTY_BITS = 28
MAX_NONCE = (1 << 63) - 1

COMMUNITY_ID = bytes.fromhex(COMMUNITY_ID_HEX)
SERVER_PUBLIC_KEY = bytes.fromhex(SERVER_PUBLIC_KEY_HEX)

LOG = logging.getLogger("lab1")


@dataclass(frozen=True)
class PowResult:
    nonce: int
    digest: bytes
    attempts: int
    elapsed_seconds: float


@dataclass(frozen=True)
class ServerReply:
    success: bool
    message: str
    responder_public_key: bytes


@dataclass
class SubmissionPayload(DataClassPayload[1]):
    email: str
    github_url: str
    nonce: int


@dataclass
class ResponsePayload(DataClassPayload[2]):
    success: bool
    message: str
