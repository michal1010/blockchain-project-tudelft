
import argparse
import logging
from static import ( MAX_NONCE, LOG,)

def configure_logging(level: str) -> None:
    logging.basicConfig(
        level=getattr(logging, level.upper(), logging.INFO),
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Lab 1 IPv8 Proof-of-Work client",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    parser.add_argument("--email", required=True, help="Your TU Delft email address")
    parser.add_argument("--github-url", required=True, help="Public GitHub repository URL for this lab")
    parser.add_argument(
        "--key-file",
        default="lab1_identity.pem",
        help="Path to the IPv8 private key file to load or create",
    )
    parser.add_argument("--port", type=int, default=8090, help="Preferred UDP port for IPv8")
    parser.add_argument(
        "--start-nonce",
        type=int,
        default=0,
        help="Nonce to start searching from, useful if you want to resume manually",
    )
    parser.add_argument(
        "--nonce",
        type=int,
        default=None,
        help="Use an already mined nonce instead of searching for one",
    )
    parser.add_argument(
        "--mine-only",
        action="store_true",
        help="Only compute and verify a nonce locally; do not start IPv8 or submit anything",
    )
    parser.add_argument(
        "--discovery-timeout",
        type=float,
        default=60*10,
        help="Seconds to wait for the server to appear in the community",
    )
    parser.add_argument(
        "--response-timeout",
        type=float,
        default=60*10.0,
        help="Seconds to wait for the server reply after sending the submission",
    )
    parser.add_argument(
        "--progress-every",
        type=int,
        default=1_000_000,
        help="How many nonces to test between mining progress logs",
    )
    parser.add_argument(
        "--log-level",
        default="INFO",
        choices=["CRITICAL", "ERROR", "WARNING", "INFO", "DEBUG"],
        help="Python logging level",
    )
    return parser.parse_args()


def clean_email(email: str) -> str:
    cleaned = email.strip()
    if cleaned != email:
        LOG.warning("Stripped surrounding whitespace from the email address before hashing/submitting.")
    return cleaned


def clean_github_url(github_url: str) -> str:
    cleaned = github_url.strip()
    if cleaned != github_url:
        LOG.warning("Stripped surrounding whitespace from the GitHub URL before hashing/submitting.")
    return cleaned


def validate_email(email: str) -> None:
    encoded = email.encode("utf-8")
    if not email:
        raise ValueError("Email must be non-empty.")
    if "\n" in email or "\r" in email:
        raise ValueError("Email must not contain newlines.")
    if len(encoded) > 254:
        raise ValueError("Email must be at most 254 UTF-8 bytes.")

    lowered = email.lower()
    valid_domain = lowered.endswith("@tudelft.nl") or lowered.endswith("@student.tudelft.nl")
    if not valid_domain:
        raise ValueError("Email must end in @tudelft.nl or @student.tudelft.nl.")


def validate_github_url(github_url: str) -> None:
    encoded = github_url.encode("utf-8")
    if not github_url:
        raise ValueError("GitHub URL must be non-empty.")
    if len(encoded) > 512:
        raise ValueError("GitHub URL must be at most 512 UTF-8 bytes.")
    for char in github_url:
        if char.isspace() or ord(char) < 0x20 or ord(char) == 0x7F:
            raise ValueError("GitHub URL must not contain whitespace or control characters.")


def validate_nonce(nonce: int) -> None:
    if not (0 <= nonce <= MAX_NONCE):
        raise ValueError(f"Nonce must satisfy 0 <= nonce <= {MAX_NONCE}.")


def build_pow_prefix(email: str, github_url: str) -> bytes:
    return email.encode("utf-8") + b"\n" + github_url.encode("utf-8") + b"\n"