# Blockchain Labs

A Python proof-of-work blockchain built on IPv8 for the TU Delft blockchain
labs. Nodes exchange signed transactions, mine blocks, synchronize missing
history, and recover from forks. Adaptive difficulty is integrated into the
blockchain, with a standalone simulation and tests in `bonus/`.

This checkout contains the Lab 3 implementation and bonus experiments. The
earlier server-registration and group-coordination labs are not included.

## Repository layout

```text
.
├── blockchain/
│   ├── node.py                       # IPv8 communities, messages, registration, and CLI
│   ├── blockchain.py                 # Blocks, hashing, PoW, validation, and chain storage
│   ├── mempool.py                    # Pending and known transactions
│   └── miner.py                      # Async mining, catch-up, and fork recovery
├── bonus/
│   ├── adaptive_difficulty.py        # Historical standalone prototype
│   ├── adaptive_difficulty_sim.py    # Simulation using the integrated blockchain
│   └── test_adaptive_difficulty.py   # Six adaptive-difficulty checks
└── README.md
```

Run all commands below from the repository root.

## Setup

The network node requires Python 3 and PyIPv8, including the `ipv8` and
`ipv8_service` modules. To create an isolated environment and install PyIPv8:

```bash
python3 -m venv .venv
source .venv/bin/activate
python3 -m pip install pyipv8
```

This repository does not pin a PyIPv8 version. If the course provides a specific
revision, install that revision into the environment instead. A `py-ipv8/`
directory inside this repository is not required by the current imports.

The bonus simulation and tests use only the Python standard library and do not
require IPv8 or a running peer network.

## Run a node

With the configured team's existing key file:

```bash
python3 blockchain/node.py --key-file key.pem
```

The default configuration in `blockchain/node.py` contains the group's ID,
server public key, and teammate public keys. IPv8 creates or reuses the key
file, but the resulting local public key **must be in the configured member
list**. A newly generated key will not match the default team keys; a mismatch
raises an error that includes the local public key.

To supply a different group and member list:

```bash
python3 blockchain/node.py \
  --key-file member1.pem \
  --port 8090 \
  --group-id YOUR_REGISTERED_GROUP_ID \
  --member-key MEMBER_1_PUBLIC_KEY_HEX \
  --member-key MEMBER_2_PUBLIC_KEY_HEX \
  --member-key MEMBER_3_PUBLIC_KEY_HEX
```

Use the complete member list on every node. For multiple nodes, use a different
key file and UDP port for each process, with each key matching its corresponding
member public key. Nodes sharing a chain must also use the same blockchain
community ID and genesis parameters. `--group-id` changes the registration
request; it does not regenerate the community ID or genesis block.

On startup, the node joins the IPv8 overlays and, unless `--no-register` is
specified, registers with the Lab 3 server. Mining waits until all configured
teammates have been discovered. `--no-register` skips server registration but
still requires the local key to be a member and waits for the configured peers.

### Command-line options

| Option | Default | Purpose |
| --- | --- | --- |
| `--key-file PATH` | `key.pem` | Private key file to create or reuse |
| `--port PORT` | `8090` | Local IPv8 UDP port |
| `--group-id ID` | `GROUP_ID` in `node.py` | Registered group identifier |
| `--community-id HEX` | `BLOCKCHAIN_COMMUNITY_ID` in `blockchain.py` | Blockchain overlay ID, exactly 20 bytes encoded as hex |
| `--member-key HEX` | `MEMBER_KEYS_HEX` in `node.py` | Member public key; repeat for the complete list, including the local key |
| `--no-register` | Off | Skip registration with the Lab 3 server |
| `--timeout SECONDS` | `300` | Server discovery and registration response timeout |
| `--mining-delay SECONDS` | `0` | Non-negative delay before each mining attempt |
| `--lie forward\|backward` | Disabled | Use dishonest timestamps for experiments |
| `--log-level LEVEL` | `INFO` | `CRITICAL`, `ERROR`, `WARNING`, `INFO`, or `DEBUG` |

Use `python3 blockchain/node.py --help` to inspect the available arguments.
Private key files (`*.pem`) are ignored by Git.

## Blockchain behavior

### Transactions and mining

Transactions contain a sender public key, data, timestamp, and digital
signature. The node verifies incoming transaction signatures and propagates
accepted transactions to teammates.

The thread-safe mempool keeps pending transactions for mining and known
transactions for recovery after a reorganization. Mining takes a snapshot of
pending transaction hashes and runs the nonce search in a worker thread. After
a block is accepted, its transactions are removed from the pending pool and the
block is broadcast to peers.

When a new chain tip arrives, the asynchronous mining task is cancelled and
restarted. Cancellation does not stop an already running worker thread; a
result produced during catch-up can be recovered if it still extends the tip.

### Validation and fork recovery

Blocks use SHA-256 hashing and a deterministic genesis block. Validation checks
the block hash, proof of work, transaction-hash commitment, parent linkage,
height, expected difficulty, and timestamp constraints. The chain is held in
memory and indexed by hash and height, with the canonical branch selected by
height.

An unknown parent triggers catch-up for an orphan above the local height:

1. Walk backward through the peer's blocks until a known ancestor is found.
2. Validate and install the replacement suffix.
3. Return known transactions from the displaced suffix to the mempool, then
   remove transactions confirmed by the replacement.
4. Query the peer's height and fetch any remaining blocks forward.

Stale orphans and concurrent catch-up attempts are ignored. Invalid data or
timeouts abort the affected fetch, and the catch-up flag is cleared when the
attempt ends.

## Adaptive difficulty

The implementation in `blockchain/blockchain.py` starts at **19 leading zero
bits** and targets **one block every 10 seconds**. Mining, block acceptance, and
suffix replacement use the same expected-difficulty calculation.

`Chain.compute_next_difficulty()` examines five consecutive timestamp intervals
ending at the selected parent, clamps each interval to 1–60 seconds, and counts
votes:

| Interval | Vote |
| --- | --- |
| Less than 5 seconds | Fast |
| 5–20 seconds, inclusive | Abstain |
| More than 20 seconds | Slow |

Difficulty increases by one when `fast - slow >= 4`, decreases by one when
`slow - fast >= 4`, and otherwise stays unchanged. It cannot decrease below
one. The initial difficulty is retained while there is insufficient history.

Timestamp validation separately requires each block to be strictly newer than
the median of up to 11 ancestor timestamps and no more than 60 seconds ahead of
the validating node's clock. Retarget votes use consecutive block timestamps,
not differences between median timestamps.

`bonus/adaptive_difficulty.py` is an earlier prototype with different retarget
rules. It is retained for reference; the node, simulation, and tests use the
integrated implementation in `blockchain/blockchain.py`.

### Network experiments

Use `--mining-delay` to delay every mining attempt, or `--lie` to generate
dishonest timestamps:

```bash
python3 blockchain/node.py \
  --key-file key.pem \
  --no-register \
  --mining-delay 5 \
  --lie forward
```

This example still requires the configured team keys and peer discovery.
`forward` adds 120 seconds to the normal candidate timestamp; `backward` uses
the parent's median-time-past floor minus 120 seconds. The lying miner bypasses
its own timestamp check when appending locally mined blocks. Honest peers
continue checking timestamps and may reject those blocks.

### Simulation

The simulation covers steady hashpower, a 10× increase, a 10× decrease, and a
dishonest timestamp every third block. It samples solve times from an
exponential distribution and inserts synthetic blocks directly into the chain,
avoiding real proof-of-work searches and normal block validation.

Set `PYTHONPATH=blockchain` when running the simulation or tests so they can
import the blockchain implementation:

```bash
PYTHONPATH=blockchain python3 bonus/adaptive_difficulty_sim.py
```

The synthetic dishonest-timestamp scenario illustrates retarget behavior; it
does not demonstrate acceptance of those timestamps by honest network peers.

### Tests

```bash
PYTHONPATH=blockchain python3 bonus/test_adaptive_difficulty.py
```

The six checks cover steady hashpower, increased difficulty after a hashpower
jump, the simulated dishonest-timestamp scenario, the median-time-past floor,
acceptance of a genuinely mined block, and deterministic retargeting. Successful
execution finishes with `All tests passed.` The real-PoW check searches for a
nonce at difficulty 19, so its runtime varies.
