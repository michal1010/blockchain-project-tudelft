from __future__ import annotations

import argparse
import asyncio
import logging
import sys
import time
from dataclasses import dataclass
from pathlib import Path
from traceback import format_exception

from cryptography.exceptions import UnsupportedAlgorithm


REPO_ROOT = Path(__file__).resolve().parent
LOCAL_IPV8_ROOT = REPO_ROOT / "py-ipv8"

if LOCAL_IPV8_ROOT.exists():
    sys.path.insert(0, str(LOCAL_IPV8_ROOT))

try:
    from ipv8.community import Community, CommunitySettings
    from ipv8.configuration import ConfigBuilder, Strategy, WalkerDefinition, default_bootstrap_defs
    from ipv8.keyvault.crypto import default_eccrypto
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


LAB2_COMMUNITY_ID = bytes.fromhex("4c61623247726f75705369676e696e6732303236")
LAB2_SERVER_PUBLIC_KEY = bytes.fromhex(
    "4c69624e61434c504b3a82e33614a342774e084af80835838d6dbdb64a537d3ddb6c1d82011a7f101553cda40"
    "cf5fa0e0fc23abd0a9c4f81322282c5b34566f6b8401f5f683031e60c96"
)

GROUP_SIZE = 3
ROUNDS = 3
LOG = logging.getLogger("lab2")


@dataclass
class RegisterPayload(DataClassPayload[1]):
    member1_key: bytes
    member2_key: bytes
    member3_key: bytes


@dataclass
class RegistrationResponsePayload(DataClassPayload[2]):
    success: bool
    group_id: str
    message: str


@dataclass
class ChallengeRequestPayload(DataClassPayload[3]):
    group_id: str


@dataclass
class ChallengeResponsePayload(DataClassPayload[4]):
    nonce: bytes
    round_number: int
    deadline: float


@dataclass
class SignatureBundlePayload(DataClassPayload[5]):
    group_id: str
    round_number: int
    sig1: bytes
    sig2: bytes
    sig3: bytes


@dataclass
class RoundResultPayload(DataClassPayload[6]):
    success: bool
    round_number: int
    rounds_completed: int
    message: str


@dataclass
class TeamChallengePayload(DataClassPayload[101]):
    group_id: str
    round_number: int
    nonce: bytes
    deadline: float


@dataclass
class TeamSignaturePayload(DataClassPayload[102]):
    group_id: str
    round_number: int
    signer_key: bytes
    signature: bytes


@dataclass
class TeamRoundDonePayload(DataClassPayload[103]):
    group_id: str
    round_number: int
    rounds_completed: int
    success: bool
    message: str


@dataclass(frozen=True)
class RegistrationResponse:
    success: bool
    group_id: str
    message: str


@dataclass(frozen=True)
class Challenge:
    nonce: bytes
    round_number: int
    deadline: float


@dataclass(frozen=True)
class RoundResult:
    success: bool
    round_number: int
    rounds_completed: int
    message: str


class Lab2Community(Community):
    community_id = LAB2_COMMUNITY_ID

    def __init__(self, settings: CommunitySettings) -> None:
        super().__init__(settings)
        self.member_keys: list[bytes] = []
        self.group_id: str | None = None
        self.rounds_completed = 0
        self.current_nonce_by_round: dict[int, bytes] = {}
        self.signatures_by_round: dict[int, dict[bytes, bytes]] = {}
        self.registration_responses: asyncio.Queue[RegistrationResponse] = asyncio.Queue()
        self.challenges: asyncio.Queue[Challenge] = asyncio.Queue()
        self.round_results: asyncio.Queue[RoundResult] = asyncio.Queue()
        self.round_progress = asyncio.Event()

        self.add_message_handler(RegistrationResponsePayload, self.on_registration_response)
        self.add_message_handler(ChallengeResponsePayload, self.on_challenge_response)
        self.add_message_handler(RoundResultPayload, self.on_round_result)
        self.add_message_handler(TeamChallengePayload, self.on_team_challenge)
        self.add_message_handler(TeamSignaturePayload, self.on_team_signature)
        self.add_message_handler(TeamRoundDonePayload, self.on_team_round_done)

    @property
    def local_key(self) -> bytes:
        return self.my_peer.public_key.key_to_bin()

    @property
    def local_member_index(self) -> int:
        return self.member_keys.index(self.local_key)

    def configure_group(self, member_keys: list[bytes], group_id: str | None = None) -> None:
        validate_member_keys(member_keys)
        self.member_keys = member_keys
        self.group_id = group_id
        if self.local_key not in member_keys:
            raise ValueError("This key file is not one of the three configured Lab 2 member keys.")

    def peer_by_key(self, public_key: bytes) -> Peer | None:
        peer = self.network.get_verified_by_public_key_bin(public_key)
        if peer is not None:
            return peer
        for discovered in self.get_peers():
            if discovered.public_key.key_to_bin() == public_key:
                return discovered
        return None

    def server_peer(self) -> Peer | None:
        return self.peer_by_key(LAB2_SERVER_PUBLIC_KEY)

    def teammate_peers(self) -> dict[bytes, Peer]:
        return {
            member_key: peer
            for member_key in self.member_keys
            if member_key != self.local_key
            if (peer := self.peer_by_key(member_key)) is not None
        }

    def submitter_key_for_round(self, round_number: int) -> bytes:
        if not (1 <= round_number <= ROUNDS):
            raise ValueError(f"Round number must be between 1 and {ROUNDS}.")
        return self.member_keys[round_number - 1]

    def is_known_member(self, peer: Peer) -> bool:
        return peer.public_key.key_to_bin() in self.member_keys

    def send_register(self, peer: Peer) -> None:
        self.ez_send(peer, RegisterPayload(*self.member_keys))

    def send_challenge_request(self, peer: Peer, group_id: str) -> None:
        self.ez_send(peer, ChallengeRequestPayload(group_id))

    def send_signature_bundle(self, peer: Peer, group_id: str, round_number: int, signatures: dict[bytes, bytes]) -> None:
        ordered = [signatures[member_key] for member_key in self.member_keys]
        self.ez_send(peer, SignatureBundlePayload(group_id, round_number, ordered[0], ordered[1], ordered[2]))

    def broadcast_team_challenge(self, group_id: str, challenge: Challenge) -> None:
        payload = TeamChallengePayload(group_id, challenge.round_number, challenge.nonce, challenge.deadline)
        for peer in self.teammate_peers().values():
            self.ez_send(peer, payload)

    def send_team_signature(self, group_id: str, round_number: int, signature: bytes, preferred_peer: Peer | None) -> None:
        payload = TeamSignaturePayload(group_id, round_number, self.local_key, signature)
        if preferred_peer is not None:
            self.ez_send(preferred_peer, payload)
        for peer in self.teammate_peers().values():
            if preferred_peer is None or peer.public_key.key_to_bin() != preferred_peer.public_key.key_to_bin():
                self.ez_send(peer, payload)

    def broadcast_round_done(self, result: RoundResult) -> None:
        if self.group_id is None:
            return
        payload = TeamRoundDonePayload(
            self.group_id,
            result.round_number,
            result.rounds_completed,
            result.success,
            result.message,
        )
        for peer in self.teammate_peers().values():
            self.ez_send(peer, payload)

    def sign_nonce(self, nonce: bytes) -> bytes:
        return self.my_peer.key.signature(nonce)

    def store_signature(self, round_number: int, signer_key: bytes, signature: bytes) -> None:
        self.signatures_by_round.setdefault(round_number, {})[signer_key] = signature
        self.round_progress.set()

    def on_packet(self, packet: tuple, warn_unknown: bool = True) -> None:
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
                result = handler(source_address, data)
                if asyncio.iscoroutine(result):
                    self.register_anonymous_task("on_packet", asyncio.ensure_future(result), ignore=(Exception,))
            except UnsupportedAlgorithm as exc:
                LOG.info("Ignoring packet from %s with an unsupported public-key curve: %s", source_address, exc)
            except Exception:
                LOG.exception("Exception occurred while handling packet!\n%s", "".join(format_exception(*sys.exc_info())))
        elif warn_unknown:
            self.logger.warning("Received unknown message: %d from (%s, %d)", msg_id, *source_address)

    @lazy_wrapper(RegistrationResponsePayload)
    def on_registration_response(self, peer: Peer, payload: RegistrationResponsePayload) -> None:
        if peer.public_key.key_to_bin() != LAB2_SERVER_PUBLIC_KEY:
            LOG.warning("Ignoring registration response from non-server peer %s", peer.public_key.key_to_bin().hex())
            return
        self.registration_responses.put_nowait(RegistrationResponse(payload.success, payload.group_id, payload.message))

    @lazy_wrapper(ChallengeResponsePayload)
    def on_challenge_response(self, peer: Peer, payload: ChallengeResponsePayload) -> None:
        if peer.public_key.key_to_bin() != LAB2_SERVER_PUBLIC_KEY:
            LOG.warning("Ignoring challenge response from non-server peer %s", peer.public_key.key_to_bin().hex())
            return
        self.challenges.put_nowait(Challenge(payload.nonce, payload.round_number, payload.deadline))

    @lazy_wrapper(RoundResultPayload)
    def on_round_result(self, peer: Peer, payload: RoundResultPayload) -> None:
        if peer.public_key.key_to_bin() != LAB2_SERVER_PUBLIC_KEY:
            LOG.warning("Ignoring round result from non-server peer %s", peer.public_key.key_to_bin().hex())
            return
        result = RoundResult(payload.success, payload.round_number, payload.rounds_completed, payload.message)
        self.round_results.put_nowait(result)
        if result.success:
            self.rounds_completed = max(self.rounds_completed, result.rounds_completed)
            self.round_progress.set()
            self.broadcast_round_done(result)

    @lazy_wrapper(TeamChallengePayload)
    def on_team_challenge(self, peer: Peer, payload: TeamChallengePayload) -> None:
        sender_key = peer.public_key.key_to_bin()
        if self.group_id != payload.group_id or not self.is_known_member(peer):
            return
        if sender_key != self.submitter_key_for_round(payload.round_number):
            LOG.warning("Ignoring round %d challenge from non-submitter member", payload.round_number)
            return
        if len(payload.nonce) != 32:
            LOG.warning("Ignoring round %d challenge with nonce length %d", payload.round_number, len(payload.nonce))
            return

        self.current_nonce_by_round[payload.round_number] = payload.nonce
        signature = self.sign_nonce(payload.nonce)
        self.store_signature(payload.round_number, self.local_key, signature)
        self.send_team_signature(payload.group_id, payload.round_number, signature, peer)
        LOG.info("Signed round %d nonce for submitter member %d", payload.round_number, self.member_keys.index(sender_key) + 1)

    @lazy_wrapper(TeamSignaturePayload)
    def on_team_signature(self, peer: Peer, payload: TeamSignaturePayload) -> None:
        sender_key = peer.public_key.key_to_bin()
        if self.group_id != payload.group_id or not self.is_known_member(peer):
            return
        if sender_key != payload.signer_key:
            LOG.warning("Ignoring signature whose claimed signer does not match the authenticated peer.")
            return
        nonce = self.current_nonce_by_round.get(payload.round_number)
        if nonce is None:
            LOG.info("Ignoring signature for round %d before seeing the nonce.", payload.round_number)
            return
        try:
            valid = peer.public_key.verify(payload.signature, nonce)
        except Exception:
            valid = False
        if not valid:
            LOG.warning("Ignoring invalid teammate signature for round %d", payload.round_number)
            return
        self.store_signature(payload.round_number, sender_key, payload.signature)
        LOG.info(
            "Collected signature %d/3 for round %d",
            len(self.signatures_by_round.get(payload.round_number, {})),
            payload.round_number,
        )

    @lazy_wrapper(TeamRoundDonePayload)
    def on_team_round_done(self, peer: Peer, payload: TeamRoundDonePayload) -> None:
        if self.group_id != payload.group_id or not self.is_known_member(peer):
            return
        expected_submitter = self.submitter_key_for_round(payload.round_number)
        if peer.public_key.key_to_bin() != expected_submitter:
            LOG.warning("Ignoring round-done message from a member who was not the round submitter.")
            return
        if payload.success:
            self.rounds_completed = max(self.rounds_completed, payload.rounds_completed)
            self.round_progress.set()
            LOG.info("Teammate reported: %s", payload.message)


def configure_logging(level: str) -> None:
    logging.basicConfig(
        level=getattr(logging, level.upper(), logging.INFO),
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )


def parse_public_key(value: str) -> bytes:
    try:
        public_key = bytes.fromhex(value.strip())
    except ValueError as exc:
        raise argparse.ArgumentTypeError(f"Invalid public key hex: {value}") from exc
    if len(public_key) != 74:
        raise argparse.ArgumentTypeError(f"Expected a 74-byte IPv8 public key, got {len(public_key)} bytes.")
    return public_key


def validate_member_keys(member_keys: list[bytes]) -> None:
    if len(member_keys) != GROUP_SIZE:
        raise ValueError(f"Exactly {GROUP_SIZE} member keys are required.")
    if len(set(member_keys)) != GROUP_SIZE:
        raise ValueError("Member keys must be unique.")


def build_ipv8_instance(key_file: Path, port: int, log_level: str) -> IPv8:
    key_file.parent.mkdir(parents=True, exist_ok=True)

    builder = ConfigBuilder().clear_keys().clear_overlays()
    builder.set_address("0.0.0.0")
    builder.set_port(port)
    builder.set_log_level(log_level)
    builder.add_key("key.pem", "curve25519", str(key_file))
    builder.add_overlay(
        "Lab2Community",
        "lab2",
        [WalkerDefinition(Strategy.RandomWalk, 30, {"timeout": 3.0})],
        default_bootstrap_defs,
        {},
        [],
    )
    return IPv8(builder.finalize(), extra_communities={"Lab2Community": Lab2Community})


def load_or_create_public_key(key_file: Path) -> bytes:
    key_file.parent.mkdir(parents=True, exist_ok=True)
    if key_file.exists():
        with key_file.open("rb") as handle:
            key = default_eccrypto.key_from_private_bin(handle.read())
    else:
        key = default_eccrypto.generate_key("curve25519")
        with key_file.open("wb") as handle:
            handle.write(key.key_to_bin())
    return key.pub().key_to_bin()


async def start_lab2(args: argparse.Namespace) -> tuple[IPv8, Lab2Community]:
    ipv8 = build_ipv8_instance(Path(args.key_file), args.port, args.log_level)
    await ipv8.start()
    community = ipv8.get_overlay(Lab2Community)
    if community is None:
        await ipv8.stop()
        raise RuntimeError("Lab2Community failed to start.")
    LOG.info("Local public key: %s", community.local_key.hex())
    return ipv8, community


async def wait_for_peer(community: Lab2Community, public_key: bytes, label: str, timeout: float) -> Peer:
    start = time.perf_counter()
    next_bootstrap = 0.0

    while True:
        peer = community.peer_by_key(public_key)
        if peer is not None:
            LOG.info("Discovered %s at %s", label, peer.address)
            return peer

        elapsed = time.perf_counter() - start
        if elapsed >= timeout:
            raise TimeoutError(f"Timed out after {timeout:.1f}s waiting for {label}.")

        now = time.perf_counter()
        if now >= next_bootstrap:
            community.bootstrap()
            next_bootstrap = now + 3.0
            LOG.info("Waiting for %s... known peers in community: %d", label, len(community.get_peers()))

        await asyncio.sleep(0.5)


async def wait_for_all_lab2_peers(community: Lab2Community, timeout: float) -> Peer:
    server = await wait_for_peer(community, LAB2_SERVER_PUBLIC_KEY, "Lab 2 server", timeout)
    deadline = time.perf_counter() + timeout
    missing = [key for key in community.member_keys if key != community.local_key]

    while missing:
        missing = [key for key in community.member_keys if key != community.local_key and community.peer_by_key(key) is None]
        if not missing:
            break
        if time.perf_counter() >= deadline:
            missing_hex = ", ".join(key.hex() for key in missing)
            raise TimeoutError(f"Timed out waiting for teammate peers: {missing_hex}")
        community.bootstrap()
        LOG.info("Waiting for %d teammate peer(s) before starting the 10-second budget.", len(missing))
        await asyncio.sleep(0.75)

    LOG.info("Server and all teammates are discovered; ready to spend the challenge budget.")
    return server


async def recv_registration_response(community: Lab2Community, timeout: float) -> RegistrationResponse:
    return await asyncio.wait_for(community.registration_responses.get(), timeout=timeout)


async def request_challenge(
    community: Lab2Community,
    server: Peer,
    group_id: str,
    round_number: int,
    timeout: float,
) -> Challenge:
    end = time.perf_counter() + timeout
    while True:
        community.send_challenge_request(server, group_id)
        challenge_task = asyncio.create_task(community.challenges.get())
        result_task = asyncio.create_task(community.round_results.get())
        done, pending = await asyncio.wait(
            {challenge_task, result_task},
            timeout=0.5,
            return_when=asyncio.FIRST_COMPLETED,
        )
        for task in pending:
            task.cancel()
        if not done:
            if time.perf_counter() >= end:
                raise TimeoutError(f"Timed out waiting for challenge round {round_number}.")
            continue
        if result_task in done:
            result = result_task.result()
            raise RuntimeError(f"Server rejected challenge request: {result.message}")

        challenge = challenge_task.result()
        if challenge.round_number == round_number:
            if len(challenge.nonce) != 32:
                raise ValueError(f"Server sent nonce with invalid length {len(challenge.nonce)}.")
            return challenge
        LOG.info("Ignoring challenge for round %d while waiting for round %d.", challenge.round_number, round_number)


async def submit_round(
    community: Lab2Community,
    server: Peer,
    group_id: str,
    round_number: int,
    challenge_timeout: float,
) -> RoundResult:
    challenge = await request_challenge(community, server, group_id, round_number, challenge_timeout)
    community.current_nonce_by_round[round_number] = challenge.nonce
    own_signature = community.sign_nonce(challenge.nonce)
    community.store_signature(round_number, community.local_key, own_signature)

    LOG.info(
        "Round %d challenge received. Deadline is %.3f UTC; collecting teammate signatures.",
        round_number,
        challenge.deadline,
    )

    next_broadcast = 0.0
    while time.time() < challenge.deadline - 0.10:
        signatures = community.signatures_by_round.get(round_number, {})
        if all(member_key in signatures for member_key in community.member_keys):
            break

        now = time.perf_counter()
        if now >= next_broadcast:
            community.broadcast_team_challenge(group_id, challenge)
            next_broadcast = now + 0.25

        community.round_progress.clear()
        try:
            await asyncio.wait_for(community.round_progress.wait(), timeout=0.05)
        except asyncio.TimeoutError:
            pass

    signatures = community.signatures_by_round.get(round_number, {})
    missing = [member_key.hex() for member_key in community.member_keys if member_key not in signatures]
    if missing:
        raise TimeoutError(f"Could not collect all signatures for round {round_number}; missing: {', '.join(missing)}")

    LOG.info("Submitting round %d bundle as member %d.", round_number, community.local_member_index + 1)
    while time.time() < challenge.deadline - 0.05:
        community.send_signature_bundle(server, group_id, round_number, signatures)
        try:
            result = await asyncio.wait_for(community.round_results.get(), timeout=0.35)
        except asyncio.TimeoutError:
            continue
        if result.round_number != round_number:
            LOG.info("Ignoring round result for round %d while submitting round %d.", result.round_number, round_number)
            continue
        LOG.info("Server result: %s", result.message)
        return result

    raise TimeoutError(f"Deadline passed before a round {round_number} result arrived.")


async def run_group_rounds(args: argparse.Namespace) -> int:
    ipv8, community = await start_lab2(args)
    try:
        community.configure_group(args.member_key, args.group_id)
        server = await wait_for_all_lab2_peers(community, args.discovery_timeout)

        while community.rounds_completed < ROUNDS:
            next_round = community.rounds_completed + 1
            submitter_key = community.submitter_key_for_round(next_round)
            if submitter_key == community.local_key:
                result = await submit_round(community, server, args.group_id, next_round, args.response_timeout)
                print(f"round_{next_round}_success={result.success}")
                print(f"round_{next_round}_message={result.message}")
                if not result.success:
                    return 1
                community.rounds_completed = max(community.rounds_completed, result.rounds_completed)
                community.broadcast_round_done(result)
            else:
                LOG.info(
                    "Waiting for member %d to submit round %d.",
                    community.member_keys.index(submitter_key) + 1,
                    next_round,
                )
                community.round_progress.clear()
                await asyncio.wait_for(community.round_progress.wait(), timeout=args.response_timeout)

        print("lab2_success=True")
        print("lab2_message=all 3 rounds completed")
        return 0
    finally:
        await ipv8.stop()


async def register_group(args: argparse.Namespace) -> int:
    ipv8, community = await start_lab2(args)
    try:
        community.configure_group(args.member_key)
        server = await wait_for_peer(community, LAB2_SERVER_PUBLIC_KEY, "Lab 2 server", args.discovery_timeout)

        end = time.perf_counter() + args.response_timeout
        while True:
            community.send_register(server)
            try:
                response = await recv_registration_response(community, timeout=0.75)
            except asyncio.TimeoutError:
                if time.perf_counter() >= end:
                    raise TimeoutError("Timed out waiting for registration response.")
                continue
            print(f"registration_success={response.success}")
            print(f"group_id={response.group_id}")
            print(f"registration_message={response.message}")
            return 0 if response.success else 1
    finally:
        await ipv8.stop()


async def show_key(args: argparse.Namespace) -> int:
    print(load_or_create_public_key(Path(args.key_file)).hex())
    return 0


def add_common_network_args(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "--key-file",
        default="lab1_identity.pem",
        help="Path to the Lab 1 IPv8 private key file to reuse for Lab 2",
    )
    parser.add_argument("--port", type=int, default=8090, help="Preferred UDP port for IPv8")
    parser.add_argument(
        "--discovery-timeout",
        type=float,
        default=300.0,
        help="Seconds to wait for the server and teammates to appear",
    )
    parser.add_argument(
        "--response-timeout",
        type=float,
        default=30.0,
        help="Seconds to wait for server responses or teammate progress",
    )
    parser.add_argument(
        "--log-level",
        default="INFO",
        choices=["CRITICAL", "ERROR", "WARNING", "INFO", "DEBUG"],
        help="Python logging level",
    )


def add_member_key_arg(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "--member-key",
        action="append",
        type=parse_public_key,
        required=True,
        help="Canonical member public key as hex. Pass exactly three times, in registration/signature order.",
    )


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Lab 2 coordinated IPv8 group signing client",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    show_parser = subparsers.add_parser("show-key", help="Print the public key for the configured Lab 1 key file")
    add_common_network_args(show_parser)

    register_parser = subparsers.add_parser("register", help="Register the three-member Lab 2 group")
    add_common_network_args(register_parser)
    add_member_key_arg(register_parser)

    run_parser = subparsers.add_parser("run", help="Run the three fast challenge rounds")
    add_common_network_args(run_parser)
    add_member_key_arg(run_parser)
    run_parser.add_argument("--group-id", required=True, help="Group id returned by the register command")

    return parser.parse_args()


async def async_main(args: argparse.Namespace) -> int:
    if args.command == "show-key":
        return await show_key(args)
    if args.command == "register":
        return await register_group(args)
    if args.command == "run":
        return await run_group_rounds(args)
    raise ValueError(f"Unsupported command: {args.command}")


def main() -> int:
    args = parse_args()
    configure_logging(args.log_level)
    try:
        return asyncio.run(async_main(args))
    except KeyboardInterrupt:
        LOG.error("Interrupted by user.")
        return 130
    except Exception as exc:
        LOG.error("%s", exc)
        LOG.error("Full exception details", exc_info=True)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
