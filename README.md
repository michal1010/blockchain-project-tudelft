# Blockchain Labs

This README covers the runnable files in:

- `lab1_server_registration/`
- `lab2_coordination/`

Run all commands from the repository root.
It is also updated to include the lab3 and bonus assignment

## Setup

The code expects the local `py-ipv8/` checkout to be present in the repository.

## Lab 1: Server Registration

Folder: `lab1_server_registration/`

Files:

- `main.py`: command-line client for mining proof-of-work and submitting it to the Lab 1 server.
- `community.py`: IPv8 community used by `main.py` for server communication.
- `static.py`: Lab 1 constants, payloads, difficulty, server key, and logging name.
- `utils.py`: argument parsing, validation, logging setup, and proof-of-work prefix helper.
- `test_pow.py`: unit tests for the proof-of-work helpers.

### Mine and Submit

Replace the email and GitHub URL with your own values:

```bash
python3 lab1_server_registration/main.py \
  --email your_name@student.tudelft.nl \
  --github-url https://github.com/your-user/your-repo
```

By default this:

1. mines a valid nonce,
2. creates or reuses `key.pem`,
3. waits for the Lab 1 server,
4. submits your email, GitHub URL, and nonce.

Successful output includes:

```text
server_success=True
server_message=...
server_public_key=...
```

### Mine Only

To compute a nonce without submitting it:

```bash
python3 lab1_server_registration/main.py \
  --email your_name@student.tudelft.nl \
  --github-url https://github.com/your-user/your-repo \
  --mine-only
```

This prints:

```text
nonce=...
hash=...
leading_zero_bits=...
```

### Submit an Existing Nonce

If you already mined a nonce:

```bash
python3 lab1_server_registration/main.py \
  --email your_name@student.tudelft.nl \
  --github-url https://github.com/your-user/your-repo \
  --nonce 123456789
```

Useful optional arguments:

- `--key-file key.pem`: key file to create or reuse.
- `--port 8090`: local IPv8 UDP port.
- `--start-nonce 0`: nonce to start mining from.
- `--discovery-timeout 600`: seconds to wait for the server.
- `--response-timeout 600`: seconds to wait for the server reply.
- `--log-level INFO`: logging level.

### Run Lab 1 Tests

```bash
cd lab1_server_registration
python3 -m unittest test_pow.py
cd ..
```

## Lab 2: Coordination

Folder: `lab2_coordination/`

Files:

- `registration.py`: command-line client for registering a three-member Lab 2 group.
- `group_submition.py`: coordination runner for the three signing rounds.

Lab 2 uses the same IPv8 key file by default: `key.pem`. Each group member needs their public key from the Lab 1 output/logs. The three public keys must be passed in the same canonical order during registration and must also match `MEMBER_KEYS_HEX` in `group_submition.py`.

### Register a Group

Run this once with the three member public keys:

```bash
python3 lab2_coordination/registration.py register \
  --key-file key.pem \
  --member-key MEMBER_1_PUBLIC_KEY_HEX \
  --member-key MEMBER_2_PUBLIC_KEY_HEX \
  --member-key MEMBER_3_PUBLIC_KEY_HEX
```

Successful output includes:

```text
registration_success=True
group_id=...
registration_message=...
```

Save the printed `group_id`; it is needed for the coordination runner.

Useful optional arguments:

- `--key-file key.pem`: Lab 2 key file. Reuse the Lab 1 key unless instructed otherwise.
- `--port 8090`: local IPv8 UDP port.
- `--discovery-timeout 300`: seconds to wait for server and teammates.
- `--response-timeout 30`: seconds to wait for responses.
- `--log-level INFO`: logging level.

### Run the Signing Coordination

Before starting, edit the constants at the top of `lab2_coordination/group_submition.py` for each member:

```python
MY_ROUND = 1
KEY_FILE = "key.pem"
GROUP_ID = "the_group_id_from_registration"
MEMBER_KEYS_HEX = [
    "member_1_public_key_hex",
    "member_2_public_key_hex",
    "member_3_public_key_hex",
]
```

Each member must set:

- `MY_ROUND = 1` for the member whose key is first in `MEMBER_KEYS_HEX`.
- `MY_ROUND = 2` for the second member.
- `MY_ROUND = 3` for the third member.
- `KEY_FILE` to that member's own private key file.
- `GROUP_ID` to the value printed by `registration.py`.

Then all three members run:

```bash
python3 lab2_coordination/group_submition.py
```

The runner waits until the Lab 2 server and both teammates are discovered. Round submission is done in the order of `MEMBER_KEYS_HEX`: member 1 submits round 1, member 2 submits round 2, and member 3 submits round 3.

## Lab 3: Blockchain

Folder: `lab3_blockchain/`

Lab 3 extends the peer-to-peer system with a blockchain layer that supports transaction propagation, proof-of-work mining, chain synchronization, fork recovery, and chain reorganization.

### Files

* `node.py` – main blockchain node implementation and network communication.
* `blockchain.py` – block, chain, validation, proof-of-work, and chain reorganization logic.
* `mempool.py` – transaction storage and recovery during forks.
* `miner.py` – asynchronous mining and catch-up mechanisms.

---

### Features

#### Blockchain

* Genesis block generation and validation
* SHA-256 block hashing
* Proof-of-work mining
* Block validation and chain validation
* Block indexing by hash and height

#### Transactions

Transactions contain:

* Sender public key
* Data payload
* Timestamp
* Digital signature

Transactions are propagated through the network and stored in a mempool until confirmed in a mined block.

#### Mempool

The mempool maintains:

* **Pending transactions** waiting to be mined
* **Known transactions** previously observed by the node

Supported operations include:

* Adding transactions
* Taking mining snapshots
* Removing confirmed transactions
* Re-adding transactions after chain reorganizations

#### Mining

Mining runs asynchronously in a background worker thread to avoid blocking network communication.

When mining:

1. The current chain tip is selected.
2. Pending transactions are collected from the mempool.
3. A candidate block is created.
4. Proof-of-work is executed.
5. The block is validated and appended to the chain.

If a new valid block is received while mining, the current mining task is cancelled and restarted on top of the new chain tip.

#### Consensus

When a block is received from a peer:

* Valid extending blocks are appended.
* Invalid blocks are rejected.
* Orphan blocks trigger the catch-up protocol.

#### Catch-Up Protocol

When a node receives a block whose parent is unknown:

**Phase 1 – Backward Walk**

* Request earlier blocks from the peer.
* Continue until a known ancestor is found.

**Phase 2 – Forward Walk**

* Query the peer's chain height.
* Fetch all missing blocks until synchronization is complete.

#### Chain Reorganization

If a longer valid chain is discovered:

1. The common ancestor is identified.
2. The old suffix is removed.
3. The new suffix is validated and installed.
4. Transactions from orphaned blocks are returned to the mempool.
5. Transactions confirmed in the winning chain are removed.

This ensures eventual consistency between nodes.

---

### Running a Blockchain Node

Run from the repository root:

```bash
python3 lab3_blockchain/node.py
```

or

```bash
python lab3_blockchain/node.py
```

The node will:

1. Start IPv8.
2. Join the blockchain overlay.
3. Register with the Lab 3 server.
4. Discover peers.
5. Begin transaction exchange and mining.

---

### Useful Command Line Arguments

```bash
python3 lab3_blockchain/node.py \
  --key-file key.pem \
  --port 8090 \
  --group-id YOUR_GROUP_ID
```

Optional arguments:

| Argument         | Description                                        |
| ---------------- | -------------------------------------------------- |
| `--key-file`     | Private key file to use                            |
| `--port`         | Local IPv8 UDP port                                |
| `--group-id`     | Registered group identifier                        |
| `--community-id` | Blockchain overlay identifier                      |
| `--member-key`   | Member public key (can be supplied multiple times) |
| `--no-register`  | Skip server registration                           |
| `--timeout`      | Registration timeout in seconds                    |
| `--log-level`    | Logging level (`INFO`, `DEBUG`, etc.)              |

---

### Running Multiple Nodes

Open multiple terminals and start several nodes using different key files and ports:

```bash
python3 lab3_blockchain/node.py \
  --key-file member1.pem \
  --port 8090
```

```bash
python3 lab3_blockchain/node.py \
  --key-file member2.pem \
  --port 8091
```

```bash
python3 lab3_blockchain/node.py \
  --key-file member3.pem \
  --port 8092
```

Nodes will automatically:

* Discover each other
* Exchange transactions
* Broadcast newly mined blocks
* Synchronize chains when forks occur
* Recover missing blocks through catch-up

---

### Implementation Highlights

* Deterministic genesis block generation
* Non-blocking asynchronous mining
* Thread-safe mempool operations
* Automatic mining restart on new chain tips
* Orphan block detection and recovery
* Fork handling through chain reorganization
* Transaction recovery during reorgs
* Full-chain validation after suffix replacement


## Bonus: Adaptive Difficulty

## What this is

The base chain mines at a fixed difficulty (12 leading zero bits), so block
times drift whenever hashpower changes. This add-on adjusts difficulty
automatically. It is **purely additive** — two new files, nothing in the
submitted code is modified.

## Files

| File | Purpose |
|---|---|
| `adaptive_difficulty.py` | The retarget logic: three functions |
| `adaptive_difficulty_sim.py` | Simulation using `Chain` and `Block` |
| `test_adaptive_difficulty.py` | Six tests verifying the properties hold |

## How it works

**`compute_next_difficulty`** looks at the last 5 block solvetimes and votes:
- solvetime > 2 × target → **slow** vote
- solvetime < target / 2 → **fast** vote
- anything between → **abstain** (normal noise)

All 5 slow → difficulty − 1. All 5 fast → difficulty + 1. Otherwise hold.

Solvetimes are clamped to [1, 6×T] before voting so a fake far-future
timestamp can only inject one bounded interval, not an arbitrarily large one.

**`median_time_past`** returns the median of the last 11 block timestamps.
New blocks must have a timestamp strictly above this. One node of three controls
~4 of 11 timestamps — not enough to move the median.

**`mine_next_block`** does a genuine nonce search at the adaptive difficulty,
with the timestamp clamped above MTP. This is the function to call in the real
node instead of the base `mine_block`.

**Why 5 blocks?** PoW solve times are exponentially distributed. At correct
difficulty, the probability any single block falls outside the dead-band and
votes "fast" is 1 − e⁻⁰·⁵ ≈ 39%. For a false trigger all 5 must agree:
0.39⁵ ≈ 0.9%. At N=4 this is 2.4% — visibly too twitchy. N=5 is the minimum
for a sub-1% false trigger rate.

## The simulation

The sim uses the `Chain` class and `Block` dataclass from
`blockchain.py`. Blocks are added via `chain._store()` and `chain._tip`
directly, bypassing only the PoW check. 

PoW is bypassed because real PoW and synthetic timestamps are incompatible:
if timestamps say blocks are arriving fast, the algorithm raises difficulty
exponentially, making real mining take minutes. The sim tests the algorithm,
not PoW. `test_mine_next_block_accepted_by_chain` tests the real PoW path.

Timestamps are generated from an exponential distribution matching the
current difficulty and hashrate — the same probability model as actual PoW.
This lets difficulty settle naturally after a hashpower jump.

## How to run


```bash
python3 bonus/adaptive_difficulty_sim.py
python3 bonus/test_adaptive_difficulty.py
```

## What to expect

**Scenario 1 (steady):** difficulty stays at 12. Solvetimes scatter — some 2s,
some 40s — but never all-5-fast or all-5-slow simultaneously.

**Scenario 2 (10x jump at block 10):** blocks arrive at 1s each, difficulty
climbs 12 → 15 over ~5 blocks, then settles. At difficulty 15 with 10x
hashpower, expected solvetime = 10 × 2³ / 10 = 8s — inside the dead-band.

**Scenario 3 (liar every 3rd block):** lie creates one clamped-to-60s solvetime
followed by one clamped-to-1s solvetime. These cancel in the vote window;
difficulty never reaches all-5 agreement and stays at 12.