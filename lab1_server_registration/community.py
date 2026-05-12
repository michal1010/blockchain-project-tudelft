from __future__ import annotations

import asyncio
import sys
import time
from pathlib import Path
from traceback import format_exception

from cryptography.exceptions import UnsupportedAlgorithm


REPO_ROOT = Path(__file__).resolve().parent
LOCAL_IPV8_ROOT = REPO_ROOT/ ".." / "py-ipv8"

if LOCAL_IPV8_ROOT.exists():
    sys.path.insert(0, str(LOCAL_IPV8_ROOT))

try:
    from ipv8.community import Community, CommunitySettings
    from ipv8.configuration import ConfigBuilder, Strategy, WalkerDefinition, default_bootstrap_defs
    from ipv8.lazy_community import lazy_wrapper
    from ipv8.messaging.payload_dataclass import DataClassPayload
    from ipv8.peer import Peer
    from ipv8_service import IPv8
except ModuleNotFoundError as exc:
    message = (
        "Could not import py-ipv8 or one of its dependencies.\n"
        "Install py-ipv8 into your Python environment, or keep a working checkout in ./py-ipv8.\n"
        f"Original import error: {exc}"
    )
    raise SystemExit(message) from exc

from static import (
    COMMUNITY_ID,
    SERVER_PUBLIC_KEY,
    ServerReply,
    SubmissionPayload,
    ResponsePayload,
    LOG,)

class Lab1Community(Community):
    community_id = COMMUNITY_ID

    def __init__(self, settings: CommunitySettings) -> None:
        super().__init__(settings)
        self.response_future: asyncio.Future[ServerReply] | None = None
        self.add_message_handler(ResponsePayload, self.on_response)

    def set_response_future(self, future: asyncio.Future[ServerReply]) -> None:
        self.response_future = future

    def get_server_peer(self) -> Peer | None:
        peer = self.network.get_verified_by_public_key_bin(SERVER_PUBLIC_KEY)
        if peer is not None:
            return peer
        for discovered in self.get_peers():
            if discovered.public_key.key_to_bin() == SERVER_PUBLIC_KEY:
                return discovered
        return None

    def send_submission(self, peer: Peer, email: str, github_url: str, nonce: int) -> None:
        self.ez_send(peer, SubmissionPayload(email, github_url, nonce))
        LOG.info("Message sent — waiting for server response...")

    def on_packet(self, packet: tuple, warn_unknown: bool = True) -> None:
        """
        Callback for when the Endpoint has new data for us.

        :param packet: The address, bytes tuple that was received.
        :param warn_unknown: Whether we should log incoming garbage data.
        """
        source_address, data = packet
        probable_peer = self.network.get_verified_by_address(source_address)
        if probable_peer:
            probable_peer.last_response = time.time()
        if self._prefix != data[:22]:
            return
        msg_id = data[22]
        handler = self.decode_map[msg_id]
        if handler is not None:
            try:
                result: asyncio.Coroutine | None = handler(source_address, data)
                if asyncio.iscoroutine(result):
                    # aw_result = cast("Awaitable", result)
                    self.register_anonymous_task("on_packet", asyncio.ensure_future(result), ignore=(Exception,))
            except UnsupportedAlgorithm as exc:
                LOG.info(
                    "Ignoring packet from %s with an unsupported public-key curve: %s",
                    source_address,
                    exc,
                )
            except Exception:
                LOG.exception("Exception occurred while handling packet!\n%s",
                                      "".join(format_exception(*sys.exc_info())))
        elif warn_unknown:
            self.logger.warning("Received unknown message: %d from (%s, %d)", msg_id, *source_address)

    @lazy_wrapper(ResponsePayload)
    def on_response(self, peer: Peer, payload: ResponsePayload) -> None:
        responder_key = peer.public_key.key_to_bin()
        if responder_key != SERVER_PUBLIC_KEY:
            LOG.warning(
                "Ignoring response from non-server peer %s",
                responder_key.hex(),
            )
            return

        if self.response_future is None or self.response_future.done():
            LOG.info("Received a server response but no pending waiter is registered.")
            return
        
        self.response_future.set_result(
            ServerReply(
                success=payload.success,
                message=payload.message,
                responder_public_key=responder_key,
            )
        )
