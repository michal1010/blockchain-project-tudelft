import random
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..'))
from lab3_blockchain.blockchain import Chain, Block, GENESIS_TIMESTAMP, DEFAULT_DIFFICULTY
from adaptive_difficulty import (
    TARGET_BLOCK_TIME as T,
    compute_next_difficulty, median_time_past, mine_next_block,
)


def _add(chain, clock, hashrate=1.0, lie=False):
    difficulty = compute_next_difficulty(chain, chain.tip)
    expected   = T * (2 ** (difficulty - DEFAULT_DIFFICULTY)) / hashrate
    solvetime  = max(1, int(random.expovariate(1.0 / expected)))
    clock     += solvetime
    timestamp  = max(clock + (100 * T if lie else 0), median_time_past(chain, chain.tip) + 1)
    height     = chain.tip.height + 1
    block = Block(
        height    = height,
        prev_hash = chain.tip.hash,
        _txs_hash = b"\x00" * 32,
        timestamp = timestamp,
        difficulty = difficulty,
        nonce     = 0,
        hash      = height.to_bytes(32, "big"),
        tx_hashes = [],
    )
    chain._store(block)
    chain._tip = block
    return block, clock


def build(n, hashrate=1.0, liar_fn=None, seed=0):
    random.seed(seed)
    liar_fn = liar_fn or (lambda i: False)
    chain, clock = Chain(), GENESIS_TIMESTAMP + 1000
    for i in range(1, n + 1):
        _, clock = _add(chain, clock, hashrate, liar_fn(i))
    return chain


def test_steady_hashpower():
    chain = build(20)
    diffs = {chain._by_hash[h].difficulty for h in chain._by_hash}
    assert diffs == {DEFAULT_DIFFICULTY}, f"difficulty moved: {diffs}"
    print("PASS  steady: difficulty stayed at", DEFAULT_DIFFICULTY)


def test_difficulty_rises_after_jump():
    chain = build(35, hashrate=10.0)
    assert chain.tip.difficulty > DEFAULT_DIFFICULTY, \
        f"difficulty did not rise, still at {chain.tip.difficulty}"
    print(f"PASS  jump: difficulty rose to {chain.tip.difficulty}")


def test_liar_cannot_move_difficulty():
    chain = build(20, liar_fn=lambda i: i % 3 == 0)
    diffs = {chain._by_hash[h].difficulty for h in chain._by_hash}
    assert diffs == {DEFAULT_DIFFICULTY}, f"liar moved difficulty: {diffs}"
    print("PASS  liar: difficulty stayed at", DEFAULT_DIFFICULTY)


def test_mtp_prevents_backdating():
    chain = build(8)
    mtp   = median_time_past(chain, chain.tip)
    block = mine_next_block(chain, timestamp=mtp)   # should be bumped above mtp
    assert block.timestamp > mtp
    print(f"PASS  MTP: timestamp corrected from {mtp} to {block.timestamp}")


def test_mine_next_block_accepted_by_chain():
    """mine_next_block produces a real PoW block that try_append accepts."""
    chain = Chain()
    block = mine_next_block(chain)
    ok, reason = chain.try_append(block)
    assert ok, f"real mined block rejected: {reason}"
    print(f"PASS  real PoW: block at difficulty {block.difficulty} accepted by try_append")


def test_retarget_is_deterministic():
    chain_a = build(15, seed=0)
    chain_b = build(15, seed=0)
    da = compute_next_difficulty(chain_a, chain_a.tip)
    db = compute_next_difficulty(chain_b, chain_b.tip)
    assert da == db, f"not deterministic: {da} != {db}"
    print(f"PASS  deterministic: both computed difficulty {da}")


if __name__ == "__main__":
    test_steady_hashpower()
    test_difficulty_rises_after_jump()
    test_liar_cannot_move_difficulty()
    test_mtp_prevents_backdating()
    test_mine_next_block_accepted_by_chain()
    test_retarget_is_deterministic()
    print("\nAll tests passed.")