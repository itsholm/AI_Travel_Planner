# Tests

This directory holds the test and benchmark scripts that are still present in the repo today.

Current files:

- `benchmark.py`: benchmark helper for comparing planning flows.
- `run_benchmark.py`: script that sends benchmark requests against a running service.
- `manual_test_session.py`: manually exercised session-store test script moved out of `app/`.

Notes:

- The older references to `test_api.py` and `test_session.py` were outdated and no longer matched the repo.
- `manual_test_session.py` is not a stable automated test yet. It is kept as a manual script for reference and later cleanup.
- Some scripts still depend on local env configuration and a running backend service.

Recommended usage:

```bash
cd tests
python benchmark.py
python run_benchmark.py
python manual_test_session.py
```
