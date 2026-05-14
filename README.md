# Blockchain Labs

This README only covers the runnable files in:

- `lab1_server_registration/`
- `lab2_coordination/`

Run all commands from the repository root.

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
