# Quickstart 

Assuming you have followed the installation process described [here](installation.md), you should be able to 
run SightHouse without any arguments to get the help: 

```bash
$ sighthouse

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
    user: "1000:1000"
    volumes:
      - ./data/redis:/data
    networks:
      - internal-net

  minio:
    image: minio/minio:RELEASE.2025-04-22T22-12-26Z
    hostname: minio
    #ports:
    #  - "9000:9000"
    #  - "9001:9001"
    environment:
      - MINIO_ROOT_USER=admin
      - MINIO_ROOT_PASSWORD=password
    command: 'minio server --console-address ":9001" /data'
    volumes:
      - ./data/minio:/data
    networks:
      - internal-net
      - external-net

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
    networks:
      - internal-net

  bsim_postgres:
    image: ghcr.io/quarkslab/sighthouse/ghidra-bsim-postgres:1.0.3
    hostname: bsim_postgres
    volumes:
      - ./data/postgres:/home/user/ghidra-data
    restart: unless-stopped
    healthcheck:
      test: ["CMD-SHELL", "/ghidra/Ghidra/Features/BSim/support/pg_is_ready.sh || exit 1 "]
      retries: 5
      interval: "30s"
      timeout: "5s"
    networks:
      - internal-net

  create_bsim_db_postgres:
    image: ghcr.io/quarkslab/sighthouse/create_bsim_db:1.0.3
    command: 'user "" bsim_postgres postgresql 5432'
    depends_on:
      bsim_postgres:
        condition: service_healthy
    restart: no
    networks:
      - internal-net

  ghidra_analyzer:
    image: ghcr.io/quarkslab/sighthouse/sighthouse-pipeline:1.0.3
    restart: unless-stopped
    command: [
      "sighthouse-pipeline/src/sighthouse/pipeline/core_modules/GhidraAnalyzer",
      "Ghidra Analyzer",
      "-w", "redis://redis:6379/0",
      "-r", "s3://minio:9000/uploads",
      "-g", "/ghidra",
    ]
    healthcheck:
      test: ["CMD-SHELL", "ls /tmp/sighthouse_Ghidra_Analyzer_*.ready 2>/dev/null | grep -q ."]
      interval: 30s
      timeout: 10s
      retries: 5
      start_period: 30s
    depends_on:
      - bsim_postgres
      - minio
      - redis
    networks:
      - internal-net

  autotools_compiler:
    image: ghcr.io/quarkslab/sighthouse/sighthouse-pipeline:1.0.3
    restart: unless-stopped
    command: [
      "sighthouse-pipeline/src/sighthouse/pipeline/core_modules/AutotoolsCompiler",
      "Autotools Compiler",
      "-w", "redis://redis:6379/0",
      "-r", "s3://minio:9000/uploads",
      "--strict"
    ]
    healthcheck:
      test: ["CMD-SHELL", "ls /tmp/sighthouse_Autotools_Compiler_*.ready 2>/dev/null | grep -q ."]
      interval: 30s
      timeout: 10s
      retries: 3
      start_period: 30s
    depends_on:
      ghidra_analyzer:
        condition: service_healthy
    networks:
      - internal-net

  git_scrapper:
    image: ghcr.io/quarkslab/sighthouse/sighthouse-pipeline:1.0.3
    restart: unless-stopped
    command: [
      "sighthouse-pipeline/src/sighthouse/pipeline/core_modules/GitScrapper",
      "Git Scrapper",
      "-w", "redis://redis:6379/0",
      "-r", "s3://minio:9000/uploads",
    ]
    healthcheck:
      test: ["CMD-SHELL", "ls /tmp/sighthouse_Git_Scrapper_*.ready 2>/dev/null | grep -q ."]
      interval: 30s
      timeout: 10s
      retries: 3
      start_period: 30s
    depends_on:
      autotools_compiler:
        condition: service_healthy
    networks:
      - internal-net
      - external-net

  create_recipe:
    image: ghcr.io/quarkslab/sighthouse/sighthouse-pipeline:1.0.3
    entrypoint: >
      /home/user/.local/bin/sighthouse pipeline -r s3://minio:9000/uploads -w redis://redis:6379/0 start pipeline.yml
    volumes:
      - ./data/pipeline.yml:/build/pipeline.yml:ro
    depends_on:
      git_scrapper:
        condition: service_healthy
    restart: on-failure
    networks:
      - internal-net

networks:
  internal-net:
    driver: bridge
    internal: true  # Blocks host access
  external-net:
    driver: bridge
```

*This setup uses one scrapper, one compiler and one analyzer but it can be easily extended to fit your needs*.

Now we need to feed some jobs into the pipeline. To accomplish this, we've created a custom YAML format, similar to 
CI/CD pipeline files, which allows you to specify which jobs should run on which workers.

Write the following content into `./data/pipeline.yml`:

```yml
# pipeline.yml
name: My pipeline
description: A simple pipeline
workers:

  - name: fetch_glibc
    package: Git Scrapper
    target: compile_glibc
    args:
      repositories:
        - name: libc
          url: git://sourceware.org/git/glibc.git
          branches:
            - glibc-2.25.90

  # Glibc cannot be compiled without optimization
  - name: compile_glibc
    package: Autotools Compiler
    target: analyzer
    foreach:
      - compiler_variants:
          x86_64-O1:
            cc: gcc
            cflags: -O1 -Wno-error=array-parameter
            configure_extra_args: --disable-werror

  - name: analyzer
    package: Ghidra Analyzer
    args:
      bsim:
        urls:
          - postgresql://user@bsim_postgres:5432/bsim
        min_instructions: 10
        max_instructions: 0
```

You can now run the pipeline using `docker compose up -d`. 



