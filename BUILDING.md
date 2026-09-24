# Test Azure CycleCloud OpenPBS Project Changes

Test CycleCloud OpenPBS changes by creating new OpenPBS clusters.

## Prerequisites
Install the [Azure CycleCloud CLI](https://learn.microsoft.com/azure/cyclecloud/how-to/install-cyclecloud-cli?view=cyclecloud-8) and confirm it is connected to your CycleCloud instance by running the following command. The expected output is `CycleCloud is configured properly`.
```bash
cyclecloud initialize
```
For local packaging, use Linux (including WSL) with Bash, a running
[Docker Engine](https://docs.docker.com/engine/install/), `unzip`, and
[`act`](https://nektosact.com/installation/index.html) on `PATH`.
The local workflow has been tested with act 0.2.89. Confirm `docker info`
succeeds without sudo and `act --version` works. Internet access is required
for container images, actions, system packages, and released dependencies.

## Local Release Build

```bash
./docker-package.sh
```

This runs only the `build` job in [.github/workflows/release.yml](.github/workflows/release.yml)
through act, using the workflow's AlmaLinux 8 container and Python 3.11.
The build targets Linux x86-64, matching the bundled RPMs. It uses your current
working tree, including uncommitted edits and nonignored new files. Git-ignored
virtual environments, dependency caches, and build outputs are not copied.
Local scalelib/API overrides and Podman are not supported by this wrapper.

Logs appear in the terminal. After a successful build, the workflow artifacts
are extracted into `blobs/` as your user. Matching filenames are overwritten;
unrelated and older-version files are preserved. A failed workflow leaves
existing blobs untouched and returns a nonzero exit status.

No GitHub token is required. The wrapper uses `workflow_dispatch`, selects only
`build`, and disables loading act's default secret, environment, variable, and
input files. Do not configure credential or execution overrides in `.actrc`
for this command. The `publish` job runs only for `2*` tag pushes, checks that
the tag matches `project.ini`, and publishes the build job's downloaded artifacts
as a prerelease. The release-upload step is additionally disabled under act.

The temporary local artifact server uses port 34567. To resolve a port conflict:

```bash
ACT_ARTIFACT_SERVER_PORT=34568 ./docker-package.sh
```

`build.sh` remains the workflow's inner packaging command; it requires the build
environment to be installed already. It does not generate or update the workflow.

Packaging and wrapper tests can be run without act or Docker:

```bash
python3 -m unittest discover -s test_packaging -v
```

To also verify dirty-source packaging, ignored build outputs, artifact ownership,
and repeat builds in an isolated checkout (requires act, Docker, and internet):

```bash
PBSPRO_TEST_ACT=1 python3 -m unittest discover -s test_packaging -p test_local_release.py -v
```

## 1. Upload to Your Storage Locker
1. Clone the `cyclecloud-pbspro` repository and make your desired changes.
2. From the root of the repository, run the following command to prepare [project blobs](https://learn.microsoft.com/azure/cyclecloud/how-to/storage-blobs?view=cyclecloud-8_).
```bash
./docker-package.sh
```
3. Run the following command then copy the name of the locker you would like to upload project blobs to.
```bash
cyclecloud locker list
```
4. Run the following command to upload project blobs to your locker.
```bash
cyclecloud project upload "LOCKER_NAME"
```
Replace `LOCKER_NAME` with the name of your locker.

## 2. Edit Your Cluster Template and Deploy a Cluster
1. Update the openpbs template to point to your changes by running the following commands.
```bash
cp templates/openpbs.txt templates/openpbs-test.txt
sed -i -e 's/\(\[*cluster-init[^]]*\)\]/\1:RELEASE_VERSION]/' -e 's/cyclecloud\/pbspro/pbspro/g' templates/openpbs-test.txt
``` 
Replace `RELEASE_VERSION` with the cyclecloud-pbspro release version (ex: `2.1.0`)
 
2.  Import the template by running the following command.
```bash
cyclecloud import_template -f templates/openpbs-test.txt -c openpbs OPENPBS_PREVIEW
```
Replace `OPENPBS_PREVIEW` with the desired name for your new cluster type.

3. Using the CycleCloud UI, create a new cluster and select `OPENPBS_PREVIEW` as the scheduler.