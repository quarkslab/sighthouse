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



Running the signature pipeline involves the following steps:

1. **Choosing which packages to use**: SightHouse was designed with modularity in mind, so each component
   is designed as a package that can be downloaded and installed. This allows you to scale and tailor
   the setup for each use case.

2. **Download & install packages**: Packages are distributed as a single TAR archive and can be installed
   using the following command: `sighthouse package install package.tar.gz`.

3. **Start each package**: Once installed, a package can be started using the command: 
   `sighthouse package run "Name of the package"`. 
   To query installed packages, you can use the following command: `sighthouse package list`.

4. **Query and inspect the pipeline**: The health of the pipeline can be monitored using various commands
   present under `sighthouse pipeline ...`. 

## Available Packages 

For now, the following packages are available:

{% generate_package_table %}

## Deploy using Docker 

Deploying all the required services with the correct setup can be time-consuming and error-prone. In order to 
simplify this process, we provided a Docker Compose file, allowing you to deploy an instance of the pipeline:

```yml 
services:
  redis:
    image: redis:7
    hostname: redis
    ports:
      - "6379:6379"
    volumes:
      - ./data/redis:/data
  minio:
    image: minio/minio:RELEASE.2025-04-22T22-12-26Z
    hostname: minio
    environment:
      - MINIO_ROOT_USER=admin
      - MINIO_ROOT_PASSWORD=password
    command: 'minio server --console-address ":9001" /data'
    volumes:
      - ./data/minio:/data
    ports:
      - "9000:9000"
      - "9001:9001"

  createbuckets:
    image: minio/minio:RELEASE.2025-04-22T22-12-26Z
    depends_on:
      - minio
    restart: on-failure
    entrypoint: >
      /bin/sh -c "
      sleep 3;
      /usr/bin/mc alias set dockerminio http://minio:9000 admin password;
      /usr/bin/mc mb dockerminio/uploads;
      /usr/bin/mc anonymous set public dockerminio/uploads;
      exit 0;
      "

  bsim_postgres:
    image: ghidra-bsim-postgres:1.0.0
    hostname: bsim_postgres
    volumes:
      - ./data/postgres:/home/user/ghidra-data
    restart: unless-stopped
    ports:
      - "5432:5432"
    healthcheck:
      test: ["CMD-SHELL", "/ghidra/Ghidra/Features/BSim/support/pg_is_ready.sh || exit 1 "]
      retries: 5
      interval: "30s"
      timeout: "5s"

  create_bsim_db_postgres:
    image: create_bsim_db:1.0.0
    command: 'user "" bsim_postgres postgresql 5432'
    depends_on:
      bsim_postgres:
        condition: service_healthy
    restart: no

  sighthouse_analyzer:
    image: sighthouse:1.0.0
    restart: unless-stopped
    command: [
      "src/sighthouse/core_modules/GhidraAnalyzer",   # PACKAGE_PATH
      "Ghidra Analyzer",                              # ANALYZER_NAME
      "-w", "redis://redis:6379/0",
      "-r", "s3://minio:9000/uploads",
      "-g", "/ghidra",
      "-b", "postgresql://user@bsim_postgres:5432/bsim"
    ]
    depends_on:
      - minio
      - redis

  sighthouse_compiler:
    image: sighthouse:1.0.0
    restart: unless-stopped
    command: [
      "src/sighthouse/core_modules/PlatformIoCompiler",   # PACKAGE_PATH
      "PlatformIo Compiler",
      "-w", "redis://redis:6379/0",
      "-r", "s3://minio:9000/uploads",
    ]
    depends_on:
      - sighthouse_analyzer
      - minio
      - redis

  sighthouse_scrapper:
    image: sighthouse:1.0.0
    restart: unless-stopped
    volumes:
      - ./data/scrapper:/data
    command: [
      "src/sighthouse/core_modules/PlatformIoScrapper",   # PACKAGE_PATH
      "PlatformIo Scrapper",
      "-w", "redis://redis:6379/0",
      "-r", "s3://minio:9000/uploads",
      "-d", "sqlite:////data/scrapper.db"
    ]
    depends_on:
      - sighthouse_compiler
      - minio
      - redis
```


*This setup uses one scrapper, one compiler and one analyzer but it can be easily extended to fit your needs*.

You can now run the pipeline using `docker compose up -d`. 



