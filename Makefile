.PHONY: setup prisma-generate dev backend frontend test check

# One-time environment setup: Python deps (incl. epinterface; semantic_priors is vendored in lib/),
# the generated Prisma client, and frontend deps. See README "Backend Setup".
setup:
	uv sync
	uv run epinterface prisma generate
	cd web && npm install

prisma-generate:
	uv run epinterface prisma generate

# Runs the FastAPI backend (:8000) and the Vite frontend (:5173) together.
# Ctrl+C stops both -- the trap kills every job in this recipe's process group.
dev:
	@trap 'kill 0' EXIT INT TERM; \
	(cd server && uv run uvicorn main:app --reload --port 8000) & \
	(cd web && npm run dev) & \
	wait

backend:
	cd server && uv run uvicorn main:app --reload --port 8000

frontend:
	cd web && npm run dev

test:
	uv run pytest

check:
	cd web && npm run check
