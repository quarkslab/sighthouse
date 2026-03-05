RD_HELP=H4sIAAAAAAAAA42VvW7bMBCAdz/FFRouBo7gLj1BpxRZuhBg1ET9AQrbcJWmA+FXyp7RT9a7IylT\
tKyWR8syyft4f6QBADbwH80TkTGnq2YM+X8CyCC0UbjlB0xyfgc0tI5RxjVkeojs+bEOypTCgFtG\
3a+hkkdVn4Qmv0o2dss4gVmWBVrSNgRdd9XdIs4yjnBuT+FqnMAlYljgWcIpZgv+tp64KMjXvBrl\
2Tsxytb+SWcGivf81aFBaaeCR1jAYqxmsRaN+M4VKq8haBBYZMp7kgVOYbJTQXNsEaVkqRnA9Uxe\
f/KcgxBsYv1pmoaNdQqyM/ccrzG6F6pe4wTgLhQXIPD73X3TSElIGCwvn0E40J5b1ESjDEcJJLu6\
mDZeIwk2j2zoDICwzTERS8QR+Ug7v0V9ibY6yNMkUeGJFo18qkrfzkMsdmhauGEmaddsCaaNZ4Js\
VZWO2NngYghslTtWksqZ11XKouDY6ormkFkcUAuoMFbw4pIeugBb7AoUKehy/bDizE8rhgfeJUhw\
g51CZMQoTmsbcsEmVFtcZSoayYIZ4riVibvCs1jVmg3ENWAqZF7tsu+XJSHtmdJzfktnJZ6DfBAy\
ug61YKKK1FG++IuMpFyEi9l87ZucYUiJWZQqr5grqhwXetofp7qBuMnpJlklXA8pvhoTevxfwnXe\
JLfAs7L7OOIv6GE89ocP8HmA5/0OR/je/x7g2D/3xwEOP1++/djB1/0RdvtX+PIywusA/dPTcBjh\
0wN0283mL4k1zNdsBwAA

default: help

help: # Show help for each of the Makefile recipes.
	@grep -E '^[a-zA-Z0-9 -]+:.*#'  Makefile | sort | while read -r l; do printf "\033[1;32m$$(echo $$l | cut -f 1 -d':')\033[00m:$$(echo $$l | cut -f 2- -d'#')\n"; done

lint: # Format with black and lint with ruff.
	@echo "[+] Linting"
	black .

type-check: # Run mypy.
	@echo "[+] Type checking"
	mypy --explicit-package-bases --config-file pyproject.toml . || true

test: # Run pytest.
	@echo "[+] Run tests"
	python -m pytest . || true 

clean: # Clean build artefacts
	@echo "[+] Clean"
	@find . -name '__pycache__' -type d -exec rm -rf {} +
	@find . -name '*.egg-info' -type d -exec rm -rf {} +
	@$(RM) poetry.lock
	@$(RM) -r dist build 

install_ghidra: # Install Sighthouse Ghidra client on your system
install_ghidra:check-env-ghidra
	@python src/sighthouse/client/install_ghidra.py $(GHIDRA_INSTALL_DIR)

install_ida: # Install Sighthouse Ida client on your system
install_ida:check-env-ida
	@python src/sighthouse/client/install_ida.py $(IDA_DIR)

install_binja: # Install Sighthouse Binary Ninja client on your system
	@python src/sighthouse/client/install_binja.py

install_radare:  # Install Sighthouse Radare client on your system
	@echo "$(RD_HELP)" | tr -d ' ' | base64 -d | gzip -d

check-env-ghidra:
ifndef GHIDRA_INSTALL_DIR
	$(error GHIDRA_INSTALL_DIR is undefined)
endif

check-env-ida:
ifndef IDA_DIR
	$(error IDA_DIR is undefined)
endif
	
