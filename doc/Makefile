
SHELL := /bin/bash

default: help

help: # Show help for each of the Makefile recipes.
	@grep -E '^[a-zA-Z0-9 -]+:.*#'  Makefile | sort | while read -r l; do printf "\033[1;32m$$(echo $$l | cut -f 1 -d':')\033[00m:$$(echo $$l | cut -f 2- -d'#')\n"; done

install: # Install requirements for building the doc
	@echo "Install mkdocs-material"
	@if [ ! -d "./venv" ]; then python3 -m venv venv; fi
	@. venv/bin/activate && pip install mkdocs-material mkdocs-plugin-inline-svg mkdocs-to-pdf 'mkdocstrings[python]' griffe-inherited-docstrings
	@# We need to install sighthouse to generate API reference because mkdocstrings does not handle namespace package correctly
	@. ./venv/bin/activate && cd ../sighthouse-core && pip install .
	@. ./venv/bin/activate && cd ../sighthouse-client && pip install .
	@. ./venv/bin/activate && cd ../sighthouse-frontend && pip install .
	@. ./venv/bin/activate && cd ../sighthouse-pipeline && pip install .

check-env:
	@if [ ! -d "./venv" ]; then \
		echo -e "\nNo venv found, please use 'make install' first\n"; \
		exit 1; \
	fi 

build: # Build the documentation
build: check-env
	@echo "Building documentation"
	@. venv/bin/activate && mkdocs build --site-dir public

serve: # Serve the documentation using local server
serve: check-env
	@echo "Serving documentation"
	@. venv/bin/activate && mkdocs serve -a '0.0.0.0:8000'

clean: # Clean build artefacts 
	@echo "Cleaning"
	@rm -rf public .cache venv
