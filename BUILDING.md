# Test Azure CycleCloud OpenPBS Project Changes

Test CycleCloud OpenPBS changes by creating new OpenPBS clusters.

## Prerequisites
Install the [Azure CycleCloud CLI](https://learn.microsoft.com/azure/cyclecloud/how-to/install-cyclecloud-cli?view=cyclecloud-8) and confirm it is connected to your CycleCloud instance by running the following command. The expected output is `CycleCloud is configured properly`.
```bash
cyclecloud initialize
```
Install a container runtime like [Docker](https://www.docker.com/) or [Podman](https://podman.io/) on your system.  

## 1. Upload to Your Storage Locker
1. Clone the `cyclecloud-pbspro` repository and make your desired changes.
2. From the root of the repository, run the following command to prepare [project blobs](https://learn.microsoft.com/azure/cyclecloud/how-to/storage-blobs?view=cyclecloud-8_) and generate `release.yml`.
```bash
./build.sh
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
Replace `RELEASE_VERSION` with the cyclecloud-pbspro release version (ex: `2.0.25`)
 
2.  Import the template by running the following command.
```bash
cyclecloud import_template -f templates/openpbs-test.txt -c openpbs OPENPBS_PREVIEW
```
Replace `OPENPBS_PREVIEW` with the desired name for your new cluster type.

3. Using the CycleCloud UI, create a new cluster and select `OPENPBS_PREVIEW` as the scheduler.