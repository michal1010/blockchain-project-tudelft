# Lab 1: Proof of Work over IPv8

Working client implementation for the TU Delft blockchain Lab 1 assignment.

## Setup

```bash
python3 -m pip install -e ./py-ipv8
```

The client also works from this repository without installation because it adds the local `py-ipv8/` checkout to `sys.path`.

## Usage

Mine and submit:

```bash
python3 main.py --email you@student.tudelft.nl --github-url https://github.com/you/blockchain-project-tudelft
```

Mine without submitting:

```bash
python3 main.py --email you@student.tudelft.nl --github-url https://github.com/you/blockchain-project-tudelft --mine-only
```

Submit a known valid nonce:

```bash
python3 main.py --email you@student.tudelft.nl --github-url https://github.com/you/blockchain-project-tudelft --nonce 123456 --submit-only
```

The default private key file is `lab1_identity.pem`. Keep it safe; it is ignored by git.
