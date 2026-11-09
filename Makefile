.PHONY: setup prisma-generate dev backend frontend test test-web check

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
	@docker info >/dev/null 2>&1 || { echo 'Starting Docker Desktop (Single Building runs need it)...'; open -a Docker || true; }
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

# Frontend logic tests (pure TS + stores) with Node's built-in runner; no extra deps.
test-web:
	cd web && node --import ./tests/register.mjs --test 'tests/**/*.test.ts'

# Components use the type scale and colour tokens in web/src/app.css; a raw px font size or
# hex colour fails the check. Mark a deliberate exception with /* raw-ok */ on the same line.
check:
	cd web && npm run check
	@! grep -rnE 'font-size:\s*[0-9]+px|#[0-9a-fA-F]{3,6}\b' web/src --include='*.svelte' | grep -v 'raw-ok' \
		|| (echo 'Use the tokens in web/src/app.css instead of the raw values above.' && false)
