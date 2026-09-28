# FAQ

**What is SightHouse, in one line?**

A tool that identifies known libraries and functions inside binaries by matching them against a
continuously updated signature database, from a plugin in your reverse-engineering tool of choice.

**Do I need to install the Signature Pipeline or the Frontend just to use a client plugin?**

Not to run them yourself, no a client plugin only needs a Frontend to talk to over HTTP. But there is currently no public SightHouse instance: if your team doesn't already run a Frontend (backed by a signature database built with the Signature Pipeline), someone will need to set one up before any client has something to query.

**How does SightHouse differ from a static/offline signature database?**

The Signature Pipeline scrapes, compiles, and analyzes open-source projects automatically and
repeatedly, so signatures get refreshed as upstream libraries release new versions, instead of
relying on a fixed, manually maintained signature set. See [Architecture](architecture.md) for
how the pipeline, frontend, and clients fit together.

**Which reverse-engineering tools are supported?**

IDA, Ghidra, and Binary Ninja plugins, plus a standalone Web client. See [SRE Clients](clients/index.md).

**How do I get a signature database to query?**

There is no public SightHouse instance today, so you'll need to build your own: run a
[Signature Pipeline](signature-pipeline/quickstart.md) to build a database from the projects you
care about, then run a [Frontend](frontend/quickstart.md) to serve it to your clients.

**I get `FATAL: database "bsim" does not exist` when running the frontend, what's wrong?**

You started the Frontend before creating the BSIM database itself. Make sure the
`create_bsim_db` step (see the Docker Compose examples in the
[Signature Pipeline Quickstart](signature-pipeline/quickstart.md) and
[Frontend Quickstart](frontend/quickstart.md)) has actually run against your `bsim_postgres`
instance and created the `bsim` database before starting the Frontend.
See [quarkslab/sighthouse#3](https://github.com/quarkslab/sighthouse/issues/3) (closed) for the original report.
