# Creating a SightHouse package 

SightHouse aim to allow researcher to create and enhance the production of signatures by 
creating custom modules tailored for their needs. A package is an abstraction that can be 
then specialized for a particular task. There are currently 4 types of packages:

- Scrapper
- Preprocessor
- Compiler
- Analyzer

Each package type shall implement a specific behavior:

- Scrapers are the first stage of the pipeline, responsible for collecting projects from various sources.
- Preprocessor will received scrapped package and download all the required dependencies for the compilation step. 
- Compilers take the projects sent by preprocessor and attempt to build the sources into object files that can then be
  analyzed by an analyzer.
- Finally, analyzers will extract all the signatures into a BSIM database with added metadata.

## Package structure 

A package is defined like Python ones, with a directory and a `__init__.py` file. The package metadata
is stored inside the `package.yml` file.

```
MyPackage/
  |-- __init__.py
  `-- package.yml
```

The package metadata is a YAML file containing the following:

```yaml
name: MyPackage
description: A cool package that I made!
version: 1.0.0
author: Me
License: MIT 
```

To install a package, one can use the following command:

```bash
$ sighthouse package install path/to/MyPackage
```

Once installed, the package can be run using:
```bash
$ sighthouse package run MyPackage
```

Here "MyPackage" refer to the "name" attribute defined in the YAML metadata file. 

Package are likely to take argument in order to run. To do so, we recommend using the `ArgumentParser` class of `arparse` package 
as SightHouse will internally examine the arguments given to pass it to the package. For instance, one can pass arguments 
for package like this: 

```bash
$ sighthouse package run "Package Name" [ARGS...]
```

## Package classes 

In order to create a package, one need to inherit from one of the 4 classes:

```py
from sighthouse.pipeline.worker import Scrapper, Preprocessor, Compiler, Analyzer

class MyScrapper(Scrapper): 

    def do_work(self, job: Job) -> None:
        """Defines the actual processing behavior for a Job instance.

        Args:
            job (Job): The Job instance to process.

        Raises:
            NotImplementedError: If not overridden in subclasses.
        """

class MyPreprocessor(Preprocessor):

    def do_work(self, job: Job) -> None:
        """Defines the actual processing behavior for a Job instance.

        Args:
            job (Job): The Job instance to process.

        Raises:
            NotImplementedError: If not overridden in subclasses.
        """

class MyCompiler(Compiler):

    def do_work(self, job: Job) -> None:
        """Defines the actual processing behavior for a Job instance.

        Args:
            job (Job): The Job instance to process.

        Raises:
            NotImplementedError: If not overridden in subclasses.
        """

class MyAnalyzer(Analyzer):

    def do_work(self, job: Job) -> None:
        """Defines the actual processing behavior for a Job instance.

        Args:
            job (Job): The Job instance to process.

        Raises:
            NotImplementedError: If not overridden in subclasses.
        """

```

The `do_work` method is the main entrypoint of the package and will be called whenever a new job need to be processed. 

The `Job.job_data` contains all the informations required for the package to operate. 
The `Job.job_data` must carry at least these informations:
```json
{
  "origin": "URI of the project (Ex: url, file, etc.)",
  "file": "<filename location on Repo>",
  "hash": "unique identifier of this project",
  "name": "name of the project",
  "version": "version of the project",
}
```
But you can add any other attributes as long as it can be serialized to JSON.
