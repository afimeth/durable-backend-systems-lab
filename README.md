# Durable Backend Systems Lab

Prevent duplicate or partial money transfers while publishing a transactional outbox job.

[![CI](https://github.com/afimeth/durable-backend-systems-lab/actions/workflows/ci.yml/badge.svg)](https://github.com/afimeth/durable-backend-systems-lab/actions)

## Run, test and demo

```sh
python app.py demo
python app.py benchmark
python app.py serve --db lab.sqlite --port 8080
python scripts/verify.py
```

Install Python 3.11+ for the evidence harness. Python implementation uses only the standard library. External paid services are not required.

## Implemented

Integer-cent SQLite ledger, payload-bound idempotency keys, BEGIN IMMEDIATE transactions, atomic debit/credit/outbox, exclusive job claims, owner-checked completion, explicit HOLD recovery, loopback HTTP API.

## Evidence and status

- **IMPLEMENTED:** runnable code and failure tests in this repository.
- **MEASURED:** [baseline](evidence/baseline.json) identifies the measured source commit. Each CI matrix job uploads a fresh `receipt.json` for its exact `GITHUB_SHA`, with actual test totals and toolchain. A receipt commit does not rewrite the measured source SHA.
- **DESIGNED:** PostgreSQL migration and tenant authentication are interview discussion extensions only.
- **NOT CLAIMED:** SQLite single-host writer locking; no PostgreSQL, ORM, migrations beyond initial schema, auth, TLS, tenant isolation, cloud deployment, currency conversion, real accounting compliance, external sink exactly-once guarantee, sustained load, or production operations.

Run `python scripts/verify.py` to regenerate ignored local receipts. Benchmark/gas/bundle reports are local measurements, not a production SLO. CI and local runs are separate evidence. Passing tests are not an independent review or an accepted production release.

## Safe CV claim

> Built a SQLite transfer API with transactional idempotency, atomic outbox jobs, concurrent overdraft/replay tests, and process-crash rollback verification.

This describes a laboratory project. It does not establish years of experience, a degree, production scale, employer history, CVEs, mainnet ownership, or independent audit credentials.

## Design and interview walkthrough

See [architecture](docs/ARCHITECTURE.md), [limitations](docs/LIMITATIONS.md), and [interview scenarios](docs/INTERVIEW_SCENARIOS.md). All inputs are synthetic. This is a fresh AI-assisted standalone implementation from public requirements; no private source, customer data, credentials or proprietary code was copied. MIT license applies to this lab.
