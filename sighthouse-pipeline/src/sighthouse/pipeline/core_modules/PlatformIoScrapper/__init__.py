from argparse import ArgumentParser
from dateutil import parser, tz
from time import time, sleep
import requests

from sighthouse.pipeline.worker import Scrapper, Job
from database import PackageDatabase, Package


class PlatformIoScrapper(Scrapper):
    """
    PlatformIo API description is available here
    https://api.registry.platformio.org/v3/openapi.yaml
    """

    DEFAULT_HOST = "api.registry.platformio.org"
    API_VERSION = "v3"
    PAGE_LIMIT = 50
    # Time for caching the packages
    REFRESH_TIME = 3600
    SLEEP_TIMER = 3600

    def __init__(
        self,
        database_url: str,
        worker_url: str,
        repo_url: str | None,
        index: bool = True,
    ):
        super().__init__("PlatformIo Scrapper", worker_url, repo_url)
        self._host = self.DEFAULT_HOST
        self._database = PackageDatabase(database_url)
        self._last_indexed = None
        self._index = index
        self._jobs = set()

    def _get_package_page(self, page: int = 1) -> dict:
        url = "https://{}/{}/search?sort=updated&limit={}&page={}".format(
            self._host, self.API_VERSION, self.PAGE_LIMIT, page
        )
        resp = requests.get(url)
        if resp.status_code != 200:
            self.log("Fail to get packages for page: {}".format(page))
            return None

        return resp.json()

    def _get_owner_packages(self, pkg: dict) -> list[Package]:
        url = "https://{}/{}/packages/{}/{}/{}".format(
            self._host,
            self.API_VERSION,
            pkg.get("owner").get("username"),
            pkg.get("type"),
            pkg.get("name"),
        )
        resp = requests.get(url)
        if resp.status_code != 200:
            self.log("Fail to get package detail for package {}".format(pkg))
            return []

        packages = []
        data = resp.json()
        for version in data.get("versions") or []:
            packages.append(
                Package(
                    pkg.get("name"),
                    version.get("name"),
                    version.get("files")[0].get("checksum").get("sha256"),
                    version.get("files")[0].get("download_url"),
                    data={
                        "updated_at": parser.parse(pkg["updated_at"])
                        .replace(tzinfo=tz.tzlocal())
                        .timestamp()
                    },
                )
            )
        return packages

    def _fetch_new_packages(self):
        run = True
        pkgs = self._get_package_page()
        limit = pkgs.get("limit")
        nb_pkgs = pkgs.get("total")
        max_page = int(nb_pkgs / limit) + 2
        # Iterate over all the packages pages
        for page in range(1, max_page):
            # Break early if needed
            if not run:
                self.log("Database is up to date, stop indexing")
                return

            self.log("Indexing package page [{}/{}]".format(page, max_page))
            json_pkgs = self._get_package_page(page)
            if not json_pkgs:
                return

            for json_pkg in json_pkgs.get("items"):
                pkgs = self._get_owner_packages(json_pkg)
                for pkg in pkgs:
                    pkg_db = self._database.get_package(pkg.hash)
                    if pkg_db and pkg_db.data.get("updated_at") < pkg.data.get(
                        "updated_at"
                    ):
                        # Package already index but has new update
                        self._database.update_package(pkg)
                        # Commit changes made to database
                        self._database.commit()
                        # self.log("Package {} updated".format(pkg))
                    elif pkg_db:
                        # We reach a package that was already indexed and has not update. Since the platformio
                        # API returns a list sorted based on updated package, all other packages will be older
                        # and no update. We stop after finishing this page.
                        run = False
                    else:
                        # Package was not indexed, add it to the database
                        self._database.add_package(pkg)
                        # Commit changes made to database
                        self._database.commit()
                        # self.log("New Package {} indexed".format(pkg))

    def index(self) -> None:
        """Index packages"""
        try:
            self.log("Searching for new package to index")
            self._fetch_new_packages()
            self._last_indexed = time()
        except requests.exceptions.ConnectionError:
            self.log("Fail to update database from remote")

    def should_index(self) -> bool:
        """Return True if the scrapper need to index, False otherwise"""
        # Look at the config
        if isinstance(self._index, bool) and not self._index:
            return False

        # At first, last indexed is not set
        if self._last_indexed is None:
            return True

        return time() - self._last_indexed >= self.REFRESH_TIME

    def do_work(self, job: Job) -> None:
        while True:
            # Index if needed
            if self.should_index():
                self.index()

            # Worker is available, push new job to the manager
            new_packages = list(
                filter(
                    lambda pkg: not pkg.submitted and pkg.hash not in self._jobs,
                    self._database.get_packages(),
                )
            )
            if len(new_packages) == 0:
                # All the packages where transmitted, nothing to do until next indexing
                self.log("Going down to sleep")
                sleep(self.SLEEP_TIMER)
            else:
                for pkg in new_packages:
                    self.log("Uploading new package: {}".format(pkg))

                    # At this point we have at least one job to return
                    self._jobs.add(pkg.hash)
                    job.job_data.update(
                        {
                            "origin": pkg.url,
                            "url": pkg.url,
                            "hash": pkg.hash,
                            "name": pkg.name,
                            "version": pkg.version,
                        }
                    )
                    self.send_task(job)
                    pkg.submitted = True
                    self._database.update_package(pkg)


def main():
    parser = ArgumentParser(description="PlatformIo Scrapper worker")
    parser.add_argument(
        "-w", "--worker-url", type=str, required=True, help="Url of the worker server"
    )
    parser.add_argument(
        "-r",
        "--repo-url",
        type=str,
        required=True,
        help="Url of the repository to upload files",
    )
    parser.add_argument(
        "-d",
        "--database",
        type=str,
        required=True,
        help="Url of the database to save the jobs",
    )
    parser.add_argument(
        "--no-index",
        action="store_false",
        default=True,
        help="Don't index new packages",
    )

    args = parser.parse_args()

    PlatformIoScrapper(
        args.database, args.worker_url, args.repo_url, index=args.no_index
    ).run()


main()
