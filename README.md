# SightHouse

<img align="right" src="./doc/docs/assets/images/logo.png" width="270">

SightHouse is a tool designed to assist reverse engineers by retrieving information and 
metadata from programs and identifying similar functions.

## Installation

SightHouse is available on Pypi.

```bash
# Install SRE clients only
pip install sighthouse-client 
# Install frontend only
pip install sighthouse-frontend
# Install pipeline only 
pip install sighthouse-pipeline
# Or install everything
pip install sighthouse[all]
```

### From sources

You can also install it from the `git` repository:
```bash
# Download the repo
git clone https://github.com/quarkslab/sighthouse && cd sighthouse 
# Make install will create a new virtual env and install sighthouse in it
make install 
```

## Build Documentation

The documentation can be build by first installing SightHouse and then serve the documentation
on a local server.

```bash
# Skip this step if you already have a local repo
git clone https://github.com/quarkslab/sighthouse && cd sighthouse/doc 
# Install dependencies
make install
# Serve the documentation
make serve
```

An online documentation is available [here](https://quarkslab.github.io/sighthouse/).

## Running unit tests

You can run unit tests locally for the default python version using:
```bash
# Skip this step if you already have a local repo
git clone https://github.com/quarkslab/sighthouse && cd sighthouse 
make test
```

## Authors

- MadSquirrels (Forgette Benoit)
- Fenrisfulsur (Babigeon Sami)

