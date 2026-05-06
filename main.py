from __future__ import annotations

import argparse
import asyncio
import hashlib
import logging
import struct
import sys
import time
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parent
LOCAL_IPV8_ROOT = REPO_ROOT / "py-ipv8"

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
    PowResult,
    ServerReply,
    SubmissionPayload,
    ResponsePayload,
    MAX_NONCE,
    DIFFICULTY_BITS,
    LOG,)

from community import Lab1Community

from utils import (configure_logging, parse_args, validate_email, validate_github_url, validate_nonce, clean_email, clean_github_url, build_pow_prefix,)



def hash_submission(prefix: bytes, nonce: int) -> bytes:
    validate_nonce(nonce)
    hasher = hashlib.sha256(prefix)
    hasher.update(struct.pack(">Q", nonce))
    return hasher.digest()


def leading_zero_bits(digest: bytes) -> int:
    zero_bits = 0
    for byte in digest:
        if byte == 0:
            zero_bits += 8
            continue
        return zero_bits + (8 - byte.bit_length())
    return len(digest) * 8


def meets_difficulty(digest: bytes, required_zero_bits: int = DIFFICULTY_BITS) -> bool:
    return leading_zero_bits(digest) >= required_zero_bits


def mine_pow(
    email: str,
    github_url: str,
    start_nonce: int = 0,
    progress_every: int = 1_000_000,
) -> PowResult:
    validate_nonce(start_nonce)
    prefix = build_pow_prefix(email, github_url)
    seed_hasher = hashlib.sha256(prefix)

    start_time = time.perf_counter()
    nonce = start_nonce
    attempts = 0

    while nonce <= MAX_NONCE:
        hasher = seed_hasher.copy()
        hasher.update(struct.pack(">Q", nonce))
        digest = hasher.digest()

        attempts += 1
        if meets_difficulty(digest):
            elapsed = time.perf_counter() - start_time
            return PowResult(nonce=nonce, digest=digest, attempts=attempts, elapsed_seconds=elapsed)

        if progress_every > 0 and attempts % progress_every == 0:
            elapsed = time.perf_counter() - start_time
            rate = attempts / elapsed if elapsed > 0 else 0.0
            LOG.info(
                "Still mining: checked %d nonces in %.1fs (%.0f nonces/sec), current nonce=%d",
                attempts,
                elapsed,
                rate,
                nonce,
            )

        nonce += 1

    raise RuntimeError("Exhausted the entire signed int64 nonce range without finding a solution.")


def format_hash(digest: bytes) -> str:
    return digest.hex()


def build_ipv8_instance(key_file: Path, port: int, log_level: str) -> IPv8:
    key_file.parent.mkdir(parents=True, exist_ok=True)

    builder = ConfigBuilder().clear_keys().clear_overlays()
    builder.set_address("0.0.0.0")
    builder.set_port(port)
    builder.set_log_level(log_level)
    builder.add_key("lab1", "curve25519", str(key_file))
    builder.add_overlay(
        "Lab1Community",
        "lab1",
        [WalkerDefinition(Strategy.RandomWalk, 30, {"timeout": 3.0})],
        default_bootstrap_defs,
        {},
        [],
    )
    return IPv8(builder.finalize(), extra_communities={"Lab1Community": Lab1Community})


async def wait_for_server_peer(community: Lab1Community, timeout: float) -> Peer:
    start = time.perf_counter()
    next_bootstrap = 0.0

    while True:
        server_peer = community.get_server_peer()
        if server_peer is not None:
            LOG.info("Discovered the Lab 1 server at %s", server_peer.address)
            return server_peer

        elapsed = time.perf_counter() - start
        if elapsed >= timeout:
            raise TimeoutError(
                f"Timed out after {timeout:.1f}s waiting for the server peer to appear in the community."
            )

        now = time.perf_counter()
        if now >= next_bootstrap:
            community.bootstrap()
            next_bootstrap = now + 5.0
            LOG.info(
                "Waiting for server discovery... known peers in community so far: %d",
                len(community.get_peers()),
            )

        await asyncio.sleep(1.0)


async def submit_solution(
    email: str,
    github_url: str,
    nonce: int,
    key_file: Path,
    port: int,
    discovery_timeout: float,
    response_timeout: float,
    log_level: str,
) -> ServerReply:
    ipv8 = build_ipv8_instance(key_file, port, log_level)
    await ipv8.start()

    try:
        community = ipv8.get_overlay(Lab1Community)
        if community is None:
            raise RuntimeError("Lab1Community failed to start.")

        LOG.info("Local public key: %s", community.my_peer.public_key.key_to_bin().hex())
        server_peer = await wait_for_server_peer(community, discovery_timeout)

        loop = asyncio.get_running_loop()
        response_future: asyncio.Future[ServerReply] = loop.create_future()
        community.set_response_future(response_future)

        LOG.info("Sending submission to verified server peer %s", server_peer.public_key.key_to_bin().hex())
        community.send_submission(server_peer, email, github_url, nonce)

        return await asyncio.wait_for(response_future, timeout=response_timeout)
    finally:
        await ipv8.stop()


async def async_main(args: argparse.Namespace) -> int:
    email = clean_email(args.email)
    github_url = clean_github_url(args.github_url)

    validate_email(email)
    validate_github_url(github_url)
    validate_nonce(args.start_nonce)

    if args.nonce is None:
        LOG.info("Starting Proof-of-Work mining for %s", email)
        pow_result = mine_pow(email, github_url, start_nonce=args.start_nonce, progress_every=args.progress_every)
    else:
        validate_nonce(args.nonce)
        digest = hash_submission(build_pow_prefix(email, github_url), args.nonce)
        pow_result = PowResult(
            nonce=args.nonce,
            digest=digest,
            attempts=1,
            elapsed_seconds=0.0,
        )

    zero_bits = leading_zero_bits(pow_result.digest)
    if not meets_difficulty(pow_result.digest):
        raise ValueError(
            f"Nonce {pow_result.nonce} is invalid for this email/URL pair: hash has {zero_bits} leading zero bits."
        )

    LOG.info(
        "Valid nonce found: %d (hash=%s, leading_zero_bits=%d, attempts=%d, elapsed=%.2fs)",
        pow_result.nonce,
        format_hash(pow_result.digest),
        zero_bits,
        pow_result.attempts,
        pow_result.elapsed_seconds,
    )

    if args.mine_only:
        print(f"nonce={pow_result.nonce}")
        print(f"hash={format_hash(pow_result.digest)}")
        print(f"leading_zero_bits={zero_bits}")
        return 0

    reply = await submit_solution(
        email=email,
        github_url=github_url,
        nonce=pow_result.nonce,
        key_file=Path(args.key_file),
        port=args.port,
        discovery_timeout=args.discovery_timeout,
        response_timeout=args.response_timeout,
        log_level=args.log_level,
    )

    print(f"server_success={reply.success}")
    print(f"server_message={reply.message}")
    print(f"server_public_key={reply.responder_public_key.hex()}")
    return 0 if reply.success else 1


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
        LOG.debug("Full exception details", exc_info=True)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
