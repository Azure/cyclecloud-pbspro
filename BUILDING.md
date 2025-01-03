# Test Azure CycleCloud OpenPBS Project Changes

Test CycleCloud OpenPBS changes by creating new OpenPBS cluster.

## Prerequisites
Install the [Azure CycleCloud CLI](https://learn.microsoft.com/azure/cyclecloud/how-to/install-cyclecloud-cli?view=cyclecloud-8) and a container runtime like [Docker](https://www.docker.com/) or [Podman](https://podman.io/) on your system.  
These instructions are for [WSL](https://learn.microsoft.com/en-us/windows/wsl/install) and assume you have already cloned the `cyclecloud-pbspro` repository and made your desired changes.

## 1. Prepare Files to Upload to Your Storage Locker
1. Navigate to the root of the `cyclecloud-pbspro` repository.
2. Run the following command.
```bash
python package.py
```
3. Navigate to `cyclecloud-pbspro/dist` and `cyclecloud-pbspro-pkg-2.0.24.tar.gz` should be present. Copy the file to `cyclecloud-pbspro/blobs` by running the following command.
```bash
sudo cp cyclecloud-pbspro-pkg-2.0.24.tar.gz ~/<path_to_repo>/cyclecloud-pbspro/blobs
```
Replace `<path_to_repo>` with the path to the cloned `cyclecloud-pbspro` repository.

4. Navigate to `cyclecloud-pbspro/blobs` and create a directory named `rpms`.
```bash
sudo mkdir rpms
```
5. Run the following command from `cyclecloud-pbspro/blobs` to get required .rpm files.
```bash
sudo curl -L -k -o rpms/cyclecloud_api-8.3.1-py2.py3-none-any.whl https://github.com/Azure/cyclecloud-pbspro/releases/download/2023-03-29-bins//cyclecloud_api-8.3.1-py2.py3-none-any.whl;
sudo curl -L -k -o rpms/hwloc-libs-1.11.9-3.el8.x86_64.rpm https://github.com/Azure/cyclecloud-pbspro/releases/download/2023-03-29-bins//hwloc-libs-1.11.9-3.el8.x86_64.rpm;
sudo curl -L -k -o rpms/openpbs-client-20.0.1-0.x86_64.rpm https://github.com/Azure/cyclecloud-pbspro/releases/download/2023-03-29-bins//openpbs-client-20.0.1-0.x86_64.rpm;
sudo curl -L -k -o rpms/openpbs-client-22.05.11-0.x86_64.rpm https://github.com/Azure/cyclecloud-pbspro/releases/download/2023-03-29-bins//openpbs-client-22.05.11-0.x86_64.rpm;
sudo curl -L -k -o rpms/openpbs-execution-20.0.1-0.x86_64.rpm https://github.com/Azure/cyclecloud-pbspro/releases/download/2023-03-29-bins//openpbs-execution-20.0.1-0.x86_64.rpm;
sudo curl -L -k -o rpms/openpbs-execution-22.05.11-0.x86_64.rpm https://github.com/Azure/cyclecloud-pbspro/releases/download/2023-03-29-bins//openpbs-execution-22.05.11-0.x86_64.rpm;
sudo curl -L -k -o rpms/openpbs-server-20.0.1-0.x86_64.rpm https://github.com/Azure/cyclecloud-pbspro/releases/download/2023-03-29-bins//openpbs-server-20.0.1-0.x86_64.rpm;
sudo curl -L -k -o rpms/openpbs-server-22.05.11-0.x86_64.rpm https://github.com/Azure/cyclecloud-pbspro/releases/download/2023-03-29-bins//openpbs-server-22.05.11-0.x86_64.rpm;
sudo curl -L -k -o rpms/pbspro-client-18.1.4-0.x86_64.rpm https://github.com/Azure/cyclecloud-pbspro/releases/download/2023-03-29-bins//pbspro-client-18.1.4-0.x86_64.rpm;
sudo curl -L -k -o rpms/pbspro-debuginfo-18.1.4-0.x86_64.rpm https://github.com/Azure/cyclecloud-pbspro/releases/download/2023-03-29-bins//pbspro-debuginfo-18.1.4-0.x86_64.rpm;
sudo curl -L -k -o rpms/pbspro-execution-18.1.4-0.x86_64.rpm https://github.com/Azure/cyclecloud-pbspro/releases/download/2023-03-29-bins//pbspro-execution-18.1.4-0.x86_64.rpm;
sudo curl -L -k -o rpms/pbspro-server-18.1.4-0.x86_64.rpm https://github.com/Azure/cyclecloud-pbspro/releases/download/2023-03-29-bins//pbspro-server-18.1.4-0.x86_64.rpm;
```
6. Move the new .rpm files to the blobs directory.
```bash 
sudo mv ~/<path_to_repo>/cyclecloud-pbspro/blobs/rpms/* ~/<path_to_repo>/cyclecloud-pbspro/blobs
```
7. You should now see the following 13 files under `cyclecloud-pbspro/blobs`
```bash
cyclecloud-pbspro-pkg-2.0.24.tar.gz        openpbs-client-20.0.1-0.x86_64.rpm     openpbs-execution-22.05.11-0.x86_64.rpm  pbspro-client-18.1.4-0.x86_64.rpm     pbspro-server-18.1.4-0.x86_64.rpm
cyclecloud_api-8.3.1-py2.py3-none-any.whl  openpbs-client-22.05.11-0.x86_64.rpm   openpbs-server-20.0.1-0.x86_64.rpm       pbspro-debuginfo-18.1.4-0.x86_64.rpm
hwloc-libs-1.11.9-3.el8.x86_64.rpm         openpbs-execution-20.0.1-0.x86_64.rpm  openpbs-server-22.05.11-0.x86_64.rpm     pbspro-execution-18.1.4-0.x86_64.rpm
```

## 2. Uploading to Your Storage Locker
1. Confirm that the Azure CycleCloud CLI is installed and connected to your CycleCloud instance by running the following command. The expected output is `CycleCloud is configured properly`.
```bash
cyclecloud initialize
```
2. If you have yet to do so, set up a storage account for your CycleCloud instance to access.
3. Run the following command and confirm the presence of the storage account you would like to upload a blob to.
```bash
cyclecloud locker list
```
4. From the root of the `cyclecloud-pbspro` repository, run the following command to upload a blob to your locker.
```bash
cyclecloud project upload "<locker name>"
```
Replace `<locker name>` with the name of your locker.

## 3. Editing Your Cluster Template and Deploying a Cluster
1. Update your openpbs template to point to your changes by running the following commands from the root of the `cyclecloud-pbspro` repository.
```bash
cp templates/openpbs.txt templates/openpbs-test.txt
sed -i -e 's/\(\[*cluster-init[^]]*\)\]/\1:2.0.24]/' -e 's/cyclecloud\/pbspro/pbspro/g' templates/openpbs-test.txt
``` 
 
2.  Import the template by running the following command.
```bash
cyclecloud import_template -f templates/openpbs-test.txt -c openpbs <openpbs-preview>
```
Replace `<openpbs-preview>` with your desired name for the new cluster

3. Using the CycleCloud UI, create a new cluster. `<openpbs-preview>` should appear as one of the scheduler options.