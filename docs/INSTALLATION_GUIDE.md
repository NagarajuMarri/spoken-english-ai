# Installation guide

Use Python 3.12+, Node 22+ and the checked-in lockfile. Create a virtual environment, install `.[dev]`, copy `.env.example` to `.env`, run `alembic upgrade head`, install frontend packages with `npm ci`, then run the backend without reload and the Vite frontend. Verify `/health/ready` before acceptance. Production installation requires the reviewed container and Compose process; never use `alembic stamp head` as schema repair.
