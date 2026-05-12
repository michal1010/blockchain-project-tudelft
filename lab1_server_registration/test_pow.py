import hashlib
import struct
import unittest
from unittest.mock import patch

import main as main


EMAIL = "student@student.tudelft.nl"
GITHUB_URL = "https://github.com/example/blockchain-project-tudelft"


class ProofOfWorkTests(unittest.TestCase):
    def test_build_pow_prefix_uses_exact_submission_bytes(self) -> None:
        self.assertEqual(
            main.build_pow_prefix(EMAIL, GITHUB_URL),
            b"student@student.tudelft.nl\n"
            b"https://github.com/example/blockchain-project-tudelft\n",
        )

    def test_hash_submission_appends_big_endian_nonce_to_prefix(self) -> None:
        prefix = main.build_pow_prefix(EMAIL, GITHUB_URL)
        nonce = 42

        expected = hashlib.sha256(prefix + struct.pack(">Q", nonce)).digest()

        self.assertEqual(main.hash_submission(prefix, nonce), expected)

    def test_hash_submission_rejects_nonce_outside_allowed_range(self) -> None:
        prefix = main.build_pow_prefix(EMAIL, GITHUB_URL)

        with self.assertRaises(ValueError):
            main.hash_submission(prefix, -1)

        with self.assertRaises(ValueError):
            main.hash_submission(prefix, main.MAX_NONCE + 1)

    def test_leading_zero_bits_counts_full_and_partial_zero_bytes(self) -> None:
        self.assertEqual(main.leading_zero_bits(bytes.fromhex("000f")), 12)
        self.assertEqual(main.leading_zero_bits(bytes.fromhex("7f")), 1)
        self.assertEqual(main.leading_zero_bits(bytes.fromhex("ff")), 0)
        self.assertEqual(main.leading_zero_bits(b""), 0)

    def test_meets_difficulty_uses_required_leading_zero_bits(self) -> None:
        digest = bytes.fromhex("000fffff")

        self.assertTrue(main.meets_difficulty(digest, required_zero_bits=12))
        self.assertFalse(main.meets_difficulty(digest, required_zero_bits=13))

    def test_mine_pow_returns_first_nonce_that_meets_difficulty(self) -> None:
        prefix = main.build_pow_prefix(EMAIL, GITHUB_URL)
        target_nonce = 3
        target_digest = main.hash_submission(prefix, target_nonce)

        def only_accept_target_nonce(digest: bytes) -> bool:
            return digest == target_digest

        with patch.object(main, "meets_difficulty", side_effect=only_accept_target_nonce):
            result = main.mine_pow(EMAIL, GITHUB_URL, start_nonce=1, progress_every=1)

        self.assertEqual(result.nonce, target_nonce)
        self.assertEqual(result.digest, target_digest)
        self.assertEqual(result.attempts, 3)
        self.assertGreaterEqual(result.elapsed_seconds, 0.0)

    def test_mine_pow_computes_real_nonce_and_prints_result(self) -> None:
        required_zero_bits = 8

        # def meets_easy_difficulty(digest: bytes) -> bool:
        #     return main.leading_zero_bits(digest) >= required_zero_bits

        # with patch.object(main, "meets_difficulty", side_effect=meets_easy_difficulty):
        result = main.mine_pow(EMAIL, GITHUB_URL, start_nonce=0, progress_every=0)
        
        zero_bits = main.leading_zero_bits(result.digest)
        if not main.meets_difficulty(result.digest):
            raise ValueError(
                f"Nonce {result.nonce} is invalid for this email/URL pair: hash has {zero_bits} leading zero bits."
            )
        
        recalculated_digest = main.hash_submission(
            main.build_pow_prefix(EMAIL, GITHUB_URL),
            result.nonce,
        )

        print(
            f"\nmined_nonce={result.nonce}\n"
            f"hash={main.format_hash(result.digest)}\n"
            f"leading_zero_bits={main.leading_zero_bits(result.digest)}\n"
            f"attempts={result.attempts}"
        )

        self.assertEqual(result.digest, recalculated_digest)
        self.assertGreaterEqual(main.leading_zero_bits(result.digest), required_zero_bits)
        self.assertEqual(result.attempts, result.nonce + 1)


if __name__ == "__main__":
    unittest.main()
