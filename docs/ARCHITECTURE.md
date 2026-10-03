# Architecture

POST /transfers -> schema + key check -> debit + credit + transfer + PENDING job in one transaction. Workers claim PENDING -> RUNNING with an owner. The local sink delivery and DONE share another transaction. A stopped worker can be marked HOLD; external effects are never silently retried.

## Tradeoff

The lab optimizes local reproducibility and an inspectable failure boundary. The architecture is intentionally small enough to explain during an interview.

## Evidence boundaries

PostgreSQL migration and tenant authentication are interview discussion extensions only.
