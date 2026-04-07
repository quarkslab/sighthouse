VERSION = 1.0.3

default: help

help: # Show help for each of the Makefile recipes.
	@grep -E '^[a-zA-Z0-9 -]+:.*#'  Makefile | sort | while read -r l; do printf "\033[1;32m$$(echo $$l | cut -f 1 -d':')\033[00m:$$(echo $$l | cut -f 2- -d'#')\n"; done

bump: # Bump the version .
	@echo "[+] Bump package version $(VERSION)"
	@# Update docker version
	@sed -i "s/VERSION=.*/VERSION=\"$(VERSION)\"/" .env
	@# Update pyprojects version
	@sed -i "s/version = .*/version = \"$(VERSION)\"/" pyproject.toml 
	@sed -i "s/version = .*/version = \"$(VERSION)\"/" sighthouse-cli/pyproject.toml 
	@sed -i "s/version = .*/version = \"$(VERSION)\"/" sighthouse-client/pyproject.toml 
	@sed -i "s/version = .*/version = \"$(VERSION)\"/" sighthouse-core/pyproject.toml 
	@sed -i "s/version = .*/version = \"$(VERSION)\"/" sighthouse-frontend/pyproject.toml 
	@sed -i "s/version = .*/version = \"$(VERSION)\"/" sighthouse-pipeline/pyproject.toml 
	@# Update pyprojects dependencies for sighthouse
	@sed -i "s/\(sighthouse[-\.][a-z]*\(>=\|==\)\)[0-9]\+\.[0-9]\+\.[0-9]\+/\1$(VERSION)/g" pyproject.toml
	@sed -i "s/\(sighthouse[-\.][a-z]*\(>=\|==\)\)[0-9]\+\.[0-9]\+\.[0-9]\+/\1$(VERSION)/g" sighthouse-cli/pyproject.toml
	@sed -i "s/\(sighthouse[-\.][a-z]*\(>=\|==\)\)[0-9]\+\.[0-9]\+\.[0-9]\+/\1$(VERSION)/g" sighthouse-client/pyproject.toml
	@sed -i "s/\(sighthouse[-\.][a-z]*\(>=\|==\)\)[0-9]\+\.[0-9]\+\.[0-9]\+/\1$(VERSION)/g" sighthouse-core/pyproject.toml
	@sed -i "s/\(sighthouse[-\.][a-z]*\(>=\|==\)\)[0-9]\+\.[0-9]\+\.[0-9]\+/\1$(VERSION)/g" sighthouse-frontend/pyproject.toml
	@sed -i "s/\(sighthouse[-\.][a-z]*\(>=\|==\)\)[0-9]\+\.[0-9]\+\.[0-9]\+/\1$(VERSION)/g" sighthouse-pipeline/pyproject.toml 
	@# Update version.py(s)
	@sed -i "s/__version__ = .*/__version__ = \"$(VERSION)\"/" src/sighthouse/version.py
	@sed -i "s/__version__ = .*/__version__ = \"$(VERSION)\"/" sighthouse-core/src/sighthouse/version.py
	@sed -i "s/__version__ = .*/__version__ = \"$(VERSION)\"/" sighthouse-client/src/sighthouse/version.py
	@sed -i "s/__version__ = .*/__version__ = \"$(VERSION)\"/" sighthouse-frontend/src/sighthouse/version.py
	@sed -i "s/__version__ = .*/__version__ = \"$(VERSION)\"/" sighthouse-cli/src/sighthouse/version.py
	@sed -i "s/__version__ = .*/__version__ = \"$(VERSION)\"/" sighthouse-pipeline/src/sighthouse/version.py
	@# Update Dockerfile FROM base image versions
	@sed -i "s|\(FROM \$${BASE_URL}/[^:]*:\)[0-9]\+\.[0-9]\+\.[0-9]\+|\1$(VERSION)|g" \
	    docker/docker-ghidra-python3/Dockerfile \
	    docker/docker-bsim-postgres/Dockerfile \
	    docker/docker-bsim-elasticsearch/create-db.docker \
	    docker/docker-bsim-elasticsearch/elastic_bsim.dockerfile \
	    docker/docker-sighthouse/Dockerfile.sighthouse \
	    docker/docker-sighthouse/Dockerfile.frontend \
	    docker/docker-sighthouse/Dockerfile.pipeline
	@# Update Dockerfile LABEL versions
	@sed -i "s/LABEL version=\"[0-9]*\.[0-9]*\.[0-9]*\"/LABEL version=\"$(VERSION)\"/" \
	    docker/docker-ghidra/Dockerfile \
	    docker/docker-bsim-elasticsearch/create-db.docker
	@# Update documentation
	@sed -i "s|\(ghcr\.io/quarkslab/sighthouse/[^:]*:\)[0-9]\+\.[0-9]\+\.[0-9]\+|\1$(VERSION)|g" \
	    doc/docs/signature-pipeline/quickstart.md \
	    doc/docs/frontend/quickstart.md

lint: # Format with black and lint with ruff.
	@echo "[+] Linting"
	@if [ ! -d "./venv" ]; then echo "No venv detected. Please use 'make install-dev' first."; exit 1; fi
	@. ./venv/bin/activate && black .

type-check: # Run mypy.
	@echo "[+] Type checking"
	@if [ ! -d "./venv" ]; then echo "No venv detected. Please use 'make install-dev' first."; exit 1; fi
	@# Only run mypy for now, maybe add pylint/ruff
	@. ./venv/bin/activate && python -m mypy --exclude build --exclude tests \
	                                         --check-untyped-defs \
	                                         --follow-untyped-imports \
	                                         --config-file sighthouse-core/pyproject.toml \
	                                         sighthouse-core
	@# Exclude core modules as well for now
	@. ./venv/bin/activate && python -m mypy --exclude build --exclude tests --exclude core_modules \
	                                         --check-untyped-defs \
	                                         --follow-untyped-imports \
	                                         --config-file sighthouse-core/pyproject.toml \
	                                         sighthouse-pipeline
	@. ./venv/bin/activate && python -m mypy --exclude build --exclude tests \
	                                         --check-untyped-defs \
	                                         --follow-untyped-imports \
	                                         --config-file sighthouse-frontend/pyproject.toml \
	                                         sighthouse-frontend

test: # Run pytest.
	@echo "[+] Run tests"
	@if [ ! -d "./venv" ]; then echo "No venv detected. Please use 'make install-dev' first."; exit 1; fi
	@# Create tmp directory if it does not exists (it's the case for github CI)
	@mkdir -p /tmp/
	@. ./venv/bin/activate && python -m pytest --cov="sighthouse" --cov-report=html \
	                                         src sighthouse-core sighthouse-pipeline \
	                                         sighthouse-client sighthouse-frontend

install-hooks: # Install git hooks
	@echo "Copy git hooks"
	@if [ -d ".git" ]; then mkdir -p .git/hooks/ && cp ./.hooks/* .git/hooks/; fi

install: # Install sighthouse in a new virtual env.
	@if [ ! -d "./venv" ]; then python3 -m venv venv; fi
	@. ./venv/bin/activate && cd sighthouse-cli && pip install .
	@. ./venv/bin/activate && cd sighthouse-core && pip install .
	@. ./venv/bin/activate && cd sighthouse-client && pip install .
	@. ./venv/bin/activate && cd sighthouse-frontend && pip install .
	@. ./venv/bin/activate && cd sighthouse-pipeline && pip install .
	@. ./venv/bin/activate && pip install .[all]

install-dev: # Install sighthouse in a new virtual env in debug mode.
install-dev: install-hooks
	@if [ ! -d "./venv" ]; then python3 -m venv venv; fi
	@. ./venv/bin/activate && cd sighthouse-cli && pip install .
	@. ./venv/bin/activate && cd sighthouse-core && pip install .
	@. ./venv/bin/activate && cd sighthouse-client && pip install .
	@. ./venv/bin/activate && cd sighthouse-frontend && pip install .
	@. ./venv/bin/activate && cd sighthouse-pipeline && pip install .
	@. ./venv/bin/activate && pip install .[all]
	@. ./venv/bin/activate && pip install pytest mypy black pytest-cov

release:
	@. ./venv/bin/activate && pip install build wheel


clean: # Clean build artefacts
	@echo "[+] Clean"
	@find . -name '__pycache__' -type d -exec rm -rf {} +
	@find . -name '*.class' -type f -delete
	@find . -name '*.egg-info' -type d -exec rm -rf {} +
	@$(RM) -rf dist build sighthouse-pipeline/build sighthouse-frontend/build sighthouse-core/build \
						sighthouse-client/build htmlcov .coverage
	
