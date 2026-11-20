# Packages
 
SightHouse was designed with modularity in mind, so each component is designed as a package
that performs a particular task, such as getting new data from a specific site, compiling a project,
or analyzing it to produce function signatures that will later be used in the frontend.
 
## How to
 
SightHouse packages can be installed in different ways using this command:
 
```bash
# Using a directory
$ sighthouse package install /path/to/package-dir
# Or a tar.gz archive
$ sighthouse package install /path/to/package.tar.gz
# Or a core package
$ sighthouse package install "Name of the core package"
```
 
- If a directory is given, it must point to a valid directory with at least two files: `__init__.py`,
  which is the entrypoint of the package, and `package.yml`, which contains the package's metadata.
 
- If a `tar.gz` file is given, it must have been bundled with the `sighthouse package export` command.
 
- If a string is given, SightHouse will search its "core package" list, that is, the one bundled
  within the `sighthouse-pipeline` Python package.
 
Once installed, the packages can be listed using the following command:
 
```bash
$ sighthouse package list
Installed  Name             Version  Description
Yes        Git Scrapper     1.0.0    Scrapper for Git projects
Yes        Ghidra Analyzer  1.0.0    Extract signatures from binaries using Ghidra
```
 
You can list all packages, including the core ones, by adding the `-a` switch:
 
```bash
$ sighthouse package list -a
Installed  Name                     Version  Description
Yes        Git Scrapper             1.0.0    Scrapper for Git projects
Yes        Ghidra Analyzer          1.0.0    Extract signatures from binaries using Ghidra
No         Linux Kernel Compiler    1.0.1    Compiler for the Linux Kernel
No         Autotools Compiler       1.0.1    Compiler for Autotools projects
No         Cmake Compiler           1.0.0    Compiler for Cmake projects
No         PlatformIo Scrapper      1.0.0    Scrapper for PlatformIo projects
No         uClibc Preprocessor      1.0.0    Preprocessor for the uClibc library
No         uClibc Compiler          1.0.1    Compiler for the uClibc library
No         Upload Scrapper          1.0.0    Scrapper to upload binaries directly to the analyzer
No         PlatformIo Preprocessor  1.0.0    Preprocessor for PlatformIo projects
No         PlatformIo Compiler      1.0.0    Compiler for PlatformIo projects
```
 
An installed package can be run using:
 
```bash
$ sighthouse package run "Package Name" [ARGS...]
```
 
Here is an example:
 
```bash
$ sighthouse package run 'Ghidra Analyzer' \
  -w redis://localhost:6379/ \
  -r s3://localhost:9000/uploads \
  -g /opt/ghidra_11.4.1_PUBLIC
[INFO/MainProcess] Connected to redis://:**@localhost:6379//
[INFO/MainProcess] mingle: searching for neighbors
[INFO/MainProcess] mingle: sync with 3 nodes
[INFO/MainProcess] mingle: sync complete
[INFO/MainProcess] celery@0jqzYhKNkwH9OMQF ready.
```
 
Most of the packages require at least two arguments:
- `-r` / `--repo`: A URL pointing to a shared repository where workers can store and retrieve files.
  You can use an S3-compatible backend, or a local directory if all your workers live on the same
  machine.
- `-w` / `--worker`: A URL pointing to a Redis queue, which allows workers to get and retrieve
  jobs.
 
An installed package can be easily shared using the `export` command:
 
```bash
$ sighthouse package export "Ghidra Analyzer" -o ghidra-analyzer.tar.gz
```
 
And finally, a package can be uninstalled using this command:
 
```bash
$ sighthouse package uninstall "Ghidra Analyzer"
```
 
 
## Available packages
 
For now, the following packages are available:

{% generate_package_table %}

Below are the descriptions of all the available SightHouse packages and how they can be used.

{% generate_package_description %}
