# Blockchain Labs

This README covers the runnable files in:

- `lab1_server_registration/`
- `lab2_coordination/`
- `lab3_blockchain/`

Run all commands from the repository root.
The Lab 3 blockchain and adaptive-difficulty bonus are documented below.

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
* Proof-of-work mining with adaptive difficulty
* Block validation and chain validation
* Block indexing by hash and height
* Median-time-past and future-timestamp validation

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

Mining starts only after all configured teammate keys have been discovered. If a
new valid block is received while mining, the current mining task is cancelled
and restarted on top of the new chain tip.

#### Consensus

When a block is received from a peer:

* Valid extending blocks are appended.
* Invalid blocks are rejected.
* Orphan blocks trigger the catch-up protocol.
* Every block must use the difficulty expected from its parent chain.
* Every timestamp must be above its parent's median time past and no more than
  60 seconds ahead of the local clock.

#### Catch-Up Protocol

When a node receives a block whose parent is unknown:

Before catch-up starts, stale orphans at or below the local height and orphans
with invalid timestamps are rejected. A second orphan cannot start another
catch-up while one is already running.

**Phase 1 – Backward Walk**

* Request earlier blocks from the peer.
* Continue until a known ancestor is found.

**Phase 2 – Forward Walk**

* Query the peer's chain height.
* Fetch all missing blocks until synchronization is complete.

The catch-up state is cleared even if a request times out or validation fails.
If proof-of-work completed in the worker thread during catch-up and the mined
block still extends the resulting tip, the node can recover and broadcast it.

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

The node will:

1. Start IPv8.
2. Join the blockchain overlay.
3. Register with the Lab 3 server.
4. Discover the configured teammates.
5. Wait until every teammate is connected.
6. Begin transaction exchange and mining.

---

### Useful Command Line Arguments

```bash
python3 lab3_blockchain/node.py \
  --key-file key.pem \
  --port 8090 \
  --group-id YOUR_GROUP_ID
```

Optional arguments:

| Argument         | Description                                                        |
| ---------------- | ------------------------------------------------------------------ |
| `--key-file`     | Private key file to use                                            |
| `--port`         | Local IPv8 UDP port                                                |
| `--group-id`     | Registered group identifier                                        |
| `--community-id` | Blockchain overlay identifier                                      |
| `--member-key`   | Member public key (repeat for every member)                         |
| `--no-register`  | Skip server registration                                           |
| `--timeout`      | Registration timeout in seconds                                    |
| `--mining-delay` | Delay before each mining attempt; useful for simulations           |
| `--lie`          | Mine with a `forward` or `backward` dishonest timestamp for testing |
| `--log-level`    | Logging level (`INFO`, `DEBUG`, etc.)                              |

The local key must be included in the configured member keys. When
`--member-key` is omitted, the constants in `MEMBER_KEYS_HEX` are used.

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
* Wait for all configured teammates before mining
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
* Adaptive difficulty checked during mining, append, and reorganization
* Median-time-past and future-time timestamp checks
* Orphan block detection with stale/concurrent catch-up guards
* Recovery of usable mining results produced during catch-up
* Fork handling through chain reorganization
* Transaction recovery during reorgs
* Full-chain validation after suffix replacement


## Bonus: Adaptive Difficulty

### What This Is

The chain starts at a difficulty of 19 leading zero bits and targets one block
every 10 seconds. The bonus retarget logic is now integrated into the main Lab
3 blockchain, so mined and received blocks use the same deterministic expected
difficulty. This lets the chain react when hashpower changes while rejecting
peers that claim an incorrect difficulty.

### Files

**All the changes are integrated into the lab3 source code. We have also prepared a simulation of the adpative difficulty mechanism in the bonus folder.**


| File | Purpose |
|---|---|
| `lab3_blockchain/blockchain.py` | Integrated retarget, timestamp validation, and adaptive mining logic |
| `bonus/adaptive_difficulty.py` | Original standalone prototype retained for reference |
| `bonus/adaptive_difficulty_sim.py` | Four-scenario simulation using the integrated `Chain` and `Block` |
| `bonus/test_adaptive_difficulty.py` | Six checks for retargeting, timestamp safety, determinism, and real PoW |

### How It Works

`Chain.compute_next_difficulty()` looks at the last five block solve times and
classifies each interval:

- More than 20 seconds: **slow** vote
- Less than 5 seconds: **fast** vote
- Between 5 and 20 seconds: abstain

Solve times are clamped to the range 1–60 seconds. Difficulty decreases by one
when `slow - fast >= 4`, increases by one when `fast - slow >= 4`, and otherwise
stays unchanged. Net-balance voting means a forward timestamp lie contributes
one slow interval followed by one fast interval, so the two votes cancel.

`median_time_past()` returns the median of up to the last 11 block timestamps.
A new block must be strictly newer than its parent's median time past and cannot
be more than 60 seconds in the future. These rules are enforced when appending a
block, replacing a suffix during reorganization, and processing catch-up data.

`mine_block()` now computes the next difficulty directly from the supplied
chain and chooses a timestamp above median time past before doing a genuine
nonce search. The miner prints the height and selected difficulty when each
attempt begins.

The same expected difficulty is validated for ordinary appends and every block
of a proposed replacement suffix, preventing a fork from bypassing retarget
rules.

### Experiments

The `--mining-delay SECONDS` flag makes a node wait before every mining
attempt (the default is `0`). Running different nodes with different delays
can simulate faster and slower miners.

The `--lie forward|backward` flag makes every locally mined block use a
dishonest timestamp. `forward` moves the timestamp ahead by the configured
future-time limit, while `backward` uses the oldest timestamp permitted by
median-time-past. The lying node bypasses its own timestamp check, but honest
peers still validate the block and may reject it. Both flags can be combined,
for example: `python3 lab3_blockchain/node.py --no-register --mining-delay 5 --lie forward`.

### Simulation

The simulation imports `Chain`, `Block`, and the adaptive-difficulty constants
from `lab3_blockchain/blockchain.py`. It generates solve times from an
exponential distribution based on the current difficulty and simulated
hashrate, then stores synthetic blocks directly to avoid performing expensive
real proof-of-work for every sample.

The scenarios cover steady hashpower, a 10× increase, a 10× decrease, and a
dishonest timestamp every third block. The test script separately verifies that
a real block produced by `mine_block()` is accepted by `Chain.try_append()`.

### Run the Simulation and Tests

```bash
python3 bonus/adaptive_difficulty_sim.py
python3 bonus/test_adaptive_difficulty.py
```

Successful tests finish with `All tests passed.` The real-PoW check can take
longer than the synthetic scenarios because the starting difficulty is 19.
