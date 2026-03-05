# Quickstart 

Assuming you have followed the installation process described [here](installation.md), you should be able to 
run SightHouse without any arguments to get the help: 

```bash
$ sighthouse

          _^_
          |@|
         =====
          #::
          #::     SightHouse v1.0.0
          #::        by: Fenrisfulsur & Madsquirrels
          #::
          #::
          #::
        ###::^-..
                 ^ ~ ~~ ~~ ~ ~ ~
                  \~~ ~~ ~ ~  ~~~~~


usage: sighthouse [-h] [--version] [-d] {package,pipeline,frontend} ...

SightHouse CLI

options:
  -h, --help            show this help message and exit
  --version             show program's version number and exit
  -d, --debug           Enable debug

COMMAND:
  {package,pipeline,frontend}
    package             Handle sighthouse package
    pipeline            Handle sighthouse pipeline
    frontend            Handle sighthouse frontend
```

To run the frontend, execute the following command:

```bash
$ sighthouse frontend -g <ghidradir> -d <database> -r <repo> start -w <worker-url> -b <bsim-url>
```

## Required Parameters

- **ghidradir**: The path to the Ghidra directory that the runner will use to analyze 
  and query signatures from programs.
- **database**: The frontend saves user and program information in a dedicated database, 
  allowing you to query analysis results. Supported database formats include SQLite and PostgreSQL.
- **repo**: A location for storing analyzed files. This can be a local directory on the filesystem or a MinIO URL.
- **worker-url**: SightHouse uses Celery workers to perform program analysis. A Redis server is required to start the frontend.
- **bsim-url**: A list of BSIM URLs that analyzers will use to query signatures.

## Example Command

Here’s a complete command to start the frontend:

```bash
$ sighthouse frontend -g /ghidra -d sqlite:////data/frontend.db \
  -r local://data start -w redis://redis:6379/0 \
  -b postgresql://user@bsim_postgres:5432/bsim
```

## User Management

SightHouse employs user-based permission management, requiring you to create a user. You can do this with the following command:

```bash
$ sighthouse frontend add-user -d <database> <user> -p <password>
```

You may leave the password option empty, which will generate a random password for the new user.

## Deploy using Docker 

Deploying all the required services with the correct setup can be time-consuming and error-prone. In order to 
simplify this process, we provided a Docker Compose file, allowing you to deploy an instance of the frontend:

```yml 
services:
  redis:
    image: redis:7
    hostname: redis
    volumes:
      - ./data/redis:/data

  bsim_postgres:
    image: ghidra-bsim-postgres:1.0.0
    hostname: bsim_postgres
    volumes:
      - ./data/postgres:/home/user/ghidra-data
    ports:
      - 5432:5432
    restart: unless-stopped
    healthcheck:
      test: ["CMD-SHELL", "/ghidra/Ghidra/Features/BSim/support/pg_is_ready.sh || exit 1 "]
      retries: 5
      interval: "30s"
      timeout: "5s"

  create_user:
    image: sighthouse:1.0.0
    entrypoint: '/home/user/.local/bin/sighthouse'
    command: 'frontend add-user -d sqlite:////data/frontend.db user -p password'
    restart: no
    volumes:
      - ./data/frontend:/data


  sighthouse_frontend:
    image: sighthouse:1.0.0
    restart: unless-stopped
    entrypoint: '/home/user/.local/bin/sighthouse'
    command: 'frontend -g /ghidra -d sqlite:////data/frontend.db -r local://data start -w redis://redis:6379/0 -b postgresql://user@bsim_postgres:5432/bsim'
    healthcheck:
      test: ["CMD-SHELL", "curl http://localhost:6671/api/v1/ping || exit 1 "]
      retries: "5"
      interval: "60s"
      timeout: "5s"
    volumes:
      - ./data/frontend:/data
    depends_on:
      - create_user
      - bsim_postgres
      - redis
    ports:
      - "6669:6671"
```

The frontend can then simply be started using `docker compose up -d`.
