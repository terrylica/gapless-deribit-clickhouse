# [1.0.0](https://github.com/terrylica/gapless-deribit-clickhouse/compare/v0.1.0...v1.0.0) (2025-12-09)


* feat!: remove ticker functionality for trades-only architecture ([cd6829d](https://github.com/terrylica/gapless-deribit-clickhouse/commit/cd6829d5d83bbaacb6c0aa8f187ee6b25e2df30e))
* refactor!: rename database to deribit.options_trades ([082f24b](https://github.com/terrylica/gapless-deribit-clickhouse/commit/082f24b5752d10d4ba66b4d9f72f23c96e19aaf6))


### Bug Fixes

* ClickHouse connection and CREATE TABLE syntax ([a619f75](https://github.com/terrylica/gapless-deribit-clickhouse/commit/a619f7594769265d63a0dd6c6d69e57bb9ebe0c6))
* replace manual ADR diagrams with proper graph-easy generated output ([7276c3c](https://github.com/terrylica/gapless-deribit-clickhouse/commit/7276c3c79a012290c4b739fcec55f8d658dedab7))
* use HTTP port 8123 for local ClickHouse and insert_df for DataFrame ([099bbb1](https://github.com/terrylica/gapless-deribit-clickhouse/commit/099bbb1c695aac381a4de98116d3902037243a5b))


### Features

* add dual-mode architecture and billing APIs ([f6b89dd](https://github.com/terrylica/gapless-deribit-clickhouse/commit/f6b89dd0ed5fe67989bc5b388b3561de84972e91))
* add pagination validation and mise ClickHouse integration ([5e00f93](https://github.com/terrylica/gapless-deribit-clickhouse/commit/5e00f933265cdd069584d0cc96f9f74c9b2e416c))
* add schema CLI for validate/diff commands ([cdd5591](https://github.com/terrylica/gapless-deribit-clickhouse/commit/cdd5591abdda02df116aae32b9245e98d3fd01ba))
* add schema-first E2E validation with contract tests ([0bd8ca1](https://github.com/terrylica/gapless-deribit-clickhouse/commit/0bd8ca12b3be752b8f2787fcdf71f28a7d842352))


### BREAKING CHANGES

* Database schema changed from deribit_options.trades
to deribit.options_trades following {exchange}.{market}_{datatype} pattern.

Changes:
- Rename schema file: deribit_trades.yaml → options_trades.yaml
- Update schema: database=deribit, table=options_trades
- Update all Python code references (6 files)
- Update contract and E2E tests
- Add mise tasks: db-init, db-drop, db-migrate with depends_post
- Add CLI commands: init, drop-legacy for migration
- Add hidden helper tasks: _check-credentials, _confirm-destructive
- Update CLAUDE.md and README.md documentation

Migration: Use `mise run db-migrate` for full migration workflow.

ADR: 2025-12-08-clickhouse-naming-convention
* This release removes all ticker (OI/Greeks) functionality
to focus on trades-only data collection.

Removed:
- fetch_ticker_snapshots() API function
- get_active_instruments() API function
- collect_ticker_snapshot() collector
- run_daemon() for ticker collection
- deribit_ticker_snapshots schema
- Ticker-related probe entries

Added:
- Input validation with fail-fast pattern for fetch_trades()
- Dynamic __version__ using importlib.metadata
- mypy strict configuration

ADR: 2025-12-05-trades-only-architecture-pivot
