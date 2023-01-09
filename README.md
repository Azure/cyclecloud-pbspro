# Azure CycleCloud OpenPBS project

OpenPBS is a highly configurable open source workload manager. See the
[OpenPBS project site](http://www.openpbs.org/) for an overview and the [PBSpro
documentation](https://www.pbsworks.com/PBSProductGT.aspx?n=Altair-PBS-Professional&c=Overview-and-Capabilities&d=Altair-PBS-Professional,-Documentation)
for more information on using, configuring, and troubleshooting OpenPBS
in general.

## Versions

OpenPBS (formerly PBS Professional OSS) is released as part of version `20.0.0`. PBSPro OSS is still available
in CycleCloud by specifying the PBSPro OSS version.

```ini
   [[[configuration]]]
   pbspro.version = 18.1.4-0
```

## Installing Manually

Note: When using the cluster that is shipped with CycleCloud, the autoscaler and default queues are already installed.

First, download the installer pkg from GitHub. For example, you can download the [2.0.21 release here](https://github.com/Azure/cyclecloud-pbspro/releases/download/2.0.21/cyclecloud-pbspro-pkg-2.0.21.tar.gz)

```bash
# Prerequisite: python3, 3.6 or newer, must be installed and in the PATH
wget https://github.com/Azure/cyclecloud-pbspro/releases/download/2.0.21/cyclecloud-pbspro-pkg-2.0.21.tar.gz
tar xzf cyclecloud-pbspro-pkg-2.0.21.tar.gz
cd cyclecloud-pbspro
# Optional, but recommended. Adds relevant resources and enables strict placement
./initialize_pbs.sh
# Optional. Sets up workq as a colocated, MPI focused queue and creates htcq for non-MPI workloads.
./initialize_default_queues.sh

# Creates the azpbs autoscaler
./install.sh  --venv /opt/cycle/pbspro/venv

# If you have jetpack available, you may use the following:
# ./generate_autoscale_json.sh --install-dir /opt/cycle/pbspro \
#                              --username $(jetpack config cyclecloud.config.username) \
#                              --password $(jetpack config cyclecloud.config.password) \
#                              --url $(jetpack config cyclecloud.config.web_server) \
#                              --cluster-name $(jetpack config cyclecloud.cluster.name)

# Otherwise insert your username, password, url, and cluster name here.
./generate_autoscale_json.sh --install-dir /opt/cycle/pbspro \
                             --username user \
                             --password password \
                             --url https://fqdn:port \
                             --cluster-name cluster_name

# lastly, run this to understand any changes that may be required.
# For example, you typically have to add the ungrouped and group_id resources
# to the /var/spool/pbs/sched_priv/sched_priv file and restart.
## [root@scheduler cyclecloud-pbspro]# azpbs validate
## ungrouped is not defined for line 'resources:' in /var/spool/pbs/sched_priv/sched_config. Please add this and restart PBS
## group_id is not defined for line 'resources:' in /var/spool/pbs/sched_priv/sched_config. Please add this and restart PBS
azpbs validate
```

## Autoscale and scalesets

In order to try and ensure that the correct VMs are provisioned for different types of jobs, CycleCloud treats autoscale of MPI and serial jobs differently in OpenPBS clusters. 

For serial jobs, multiple VM scalesets (VMSS) are used in order to scale as quickly as possible. For MPI jobs to use the InfiniBand fabric for those instances that support it, all of the nodes allocated to the job have to be deployed in the same VMSS. CycleCloud
handles this by using a `PlacementGroupId` that groups nodes with the same id into the same VMSS. By default, the `workq` appends
the equivalent of `-l place=scatter:group=group_id` by using native queue defaults.

## Hooks

Our PBS integration uses 3 different PBS hooks. `autoscale` does the bulk of the work required to scale the cluster up and down. All relevant log messages can be seen in `/opt/cycle/pbspro/autoscale.log`. `cycle_sub_hook` will validate jobs unless they use `-l nodes` syntax, in which case those jobs are held and later processed by our last hook `cycle_sub_hook_periodic`.

### Autoscale Hook
The most important is the `autoscale` plugin, which runs by default on a 15 second interval. You can adjust this frequency by running
```bash
qmgr -c "set hook autoscale freq=NUM_SECONDS"
```

### Submission Hooks
`cycle_sub_hook` will validate that your job has the proper placement restrictions set. If it encounters a problem, it will output a detailed message on why the job was rejected and how to resolve the issue. For example

```bash
$> echo sleep 300 | qsub -l select=2 -l place=scatter
```
```qsub: Job uses more than one node and does not place the jobs based on group_id, which may cause issues with tightly coupled jobs.
Please do one of the following
    1) Ensure this placement is set by adding group=group_id to your -l place= statement
        Note: Queue workq's resource_defaults.place=group=group_id
    2) Add -l skipcyclesubhook=true on this job
        Note: If the resource does not exist, create it -> qmgr -c 'create resource skipcyclesubhook type=boolean'
    3) Disable this hook for this queue via queue defaults -> qmgr -c 'set queue workq resources_default.skipcyclesubhook=true'
    4) Disable this plugin - 'qmgr -c 'set hook cycle_sub_hook enabled=false'
        Note: Disabling this plugin may prevent -l nodes= style submissions from working properly.
```

One important note: if you are using `Torque` style submissions, i.e. those that uses `-l nodes` instead of `-l select`, PBS will simply convert that submission into an equivalent `-l select` style submission. However, the default placement defined for the queue is not respected by PBS when converting the job. To get around this, we will `hold` the job and our last hook, `cycle_sub_hook_periodic` will periodically update the job's placement and release it.


## Configuring Resources
The cyclecloud-pbspro application matches PBS resources to azure cloud resources 
to provide rich autoscaling and cluster configuration tools. The application will be deployed
automatically for clusters created via the CycleCloud UI or it can be installed on any 
PBS admin host on an existing cluster. For more information on defining resources in _autoscale.json_, see [ScaleLib's documentation](https://github.com/Azure/cyclecloud-scalelib/blob/master/README.md).

The default resources defined with the cluster template we ship with are

```json
{"default_resources": [
   {
      "select": {},
      "name": "ncpus",
      "value": "node.vcpu_count"
   },
   {
      "select": {},
      "name": "group_id",
      "value": "node.placement_group"
   },
   {
      "select": {},
      "name": "host",
      "value": "node.hostname"
   },
   {
      "select": {},
      "name": "mem",
      "value": "node.memory"
   },
   {
      "select": {},
      "name": "vm_size",
      "value": "node.vm_size"
   },
   {
      "select": {},
      "name": "disk",
      "value": "size::20g"
   }]
}
```

Note that disk is currently hardcoded to `size::20g` because of platform limitations to determine how much disk a node will
have. Here is an example of handling VM Size specific disk size
```json
   {
      "select": {"node.vm_size": "Standard_F2"},
      "name": "disk",
      "value": "size::20g"
   },
   {
      "select": {"node.vm_size": "Standard_H44rs"},
      "name": "disk",
      "value": "size::2t"
   }
   ```

# azpbs cli
The `azpbs` cli is the main interface for all autoscaling behavior. Note that it has a fairly powerful autocomplete capabilities. For example, typing `azpbs create_nodes --vm-size ` and then you can tab-complete the list of possible VM Sizes. Autocomplete information is updated every `azpbs autoscale` cycle, but can also be refreshed manually by running `azpbs refresh_autocomplete`.

| Command | Description |
| :---    | :---        |
| autoscale            | End-to-end autoscale process, including creation, deletion and joining of nodes. |
| buckets              | Prints out autoscale bucket information, like limits etc |
| config               | Writes the effective autoscale config, after any preprocessing, to stdout |
| create_nodes         | Create a set of nodes given various constraints. A CLI version of the nodemanager interface. |
| default_output_columns | Output what are the default output columns for an optional command. |
| delete_nodes         | Deletes node, including draining post delete handling |
| demand               | Dry-run version of autoscale. |
| initconfig           | Creates an initial autoscale config. Writes to stdout |
| jobs                 | Writes out autoscale jobs as json. Note: Running jobs are excluded. |
| join_nodes           | Adds selected nodes to the scheduler |
| limits               | Writes a detailed set of limits for each bucket. Defaults to json due to number of fields. |
| nodes                | Query nodes |
| refresh_autocomplete | Refreshes local autocomplete information for cluster specific resources and nodes. |
| remove_nodes         | Removes the node from the scheduler without terminating the actual instance. |
| retry_failed_nodes   | Retries all nodes in a failed state. |
| shell                | Interactive python shell with relevant objects in local scope. Use --script to run python scripts |
| validate             | Runs basic validation of the environment |
| validate_constraint  | Validates then outputs as json one or more constraints. |


## azpbs buckets
Use the `azpbs buckets` command to see which buckets of compute are available, how many are available, and what resources they have.
```bash
azpbs buckets --output-columns nodearray,placement_group,vm_size,ncpus,mem,available_count
```
```
NODEARRAY PLACEMENT_GROUP     VM_SIZE         NCPUS MEM     AVAILABLE_COUNT
execute                       Standard_F2s_v2 1     4.00g   50             
execute                       Standard_D2_v4  1     8.00g   50             
execute                       Standard_E2s_v4 1     16.00g  50             
execute                       Standard_NC6    6     56.00g  16             
execute                       Standard_A11    16    112.00g 6              
execute   Standard_F2s_v2_pg0 Standard_F2s_v2 1     4.00g   50             
execute   Standard_F2s_v2_pg1 Standard_F2s_v2 1     4.00g   50             
execute   Standard_D2_v4_pg0  Standard_D2_v4  1     8.00g   50             
execute   Standard_D2_v4_pg1  Standard_D2_v4  1     8.00g   50             
execute   Standard_E2s_v4_pg0 Standard_E2s_v4 1     16.00g  50             
execute   Standard_E2s_v4_pg1 Standard_E2s_v4 1     16.00g  50             
execute   Standard_NC6_pg0    Standard_NC6    6     56.00g  16             
execute   Standard_NC6_pg1    Standard_NC6    6     56.00g  16             
execute   Standard_A11_pg0    Standard_A11    16    112.00g 6              
execute   Standard_A11_pg1    Standard_A11    16    112.00g 6
```


## azpbs demand
It is common that you want to test out autoscaling without actually allocating anything. `azpbs demand` is a dry-run
version of `azpbs autoscale`. Here is a simple example where we allocate two machines for a simple `-l select=2` submission. As
you can see, job id `1` is using one `ncpus` on two different nodes. 
```bash
azpbs demand
```
```azpbs demand  --output-columns name,job_id,/ncpus
NAME      JOB_IDS NCPUS
execute-1 1       0/1  
execute-2 1       0/1
```

## azpbs create_nodes
Manually creating nodes via `azpbs create_nodes` is also quite powerful. Note that it also has a `--dry-run` mode as well.

Here is an example of allocating 100 `slots` of `mem=memory::1g` or 1gb partitions. Since our nodes have 4gb each, then we expect 25 nodes to be created.
```bash
azpbs create_nodes --keep-alive --vm-size Standard_F2s_v2 --slots 100 --constraint-expr mem=memory::1g --dry-run --output-columns name,/mem
```
```
NAME       MEM        
execute-1  0.00g/4.00g
...
execute-25 0.00g/4.00g
```

## azpbs delete_/remove_nodes
`azpbs` supports safely removing a node from PBS. The different between `delete_nodes` and `remove_nodes` is simply that `delete_nodes`, on top of removing the node from PBS, will also delete the node. You may delete by hostname or node name. Pass in `*` to delete/remove all nodes.


## azpbs shell
`azpbs shell` is a more advanced command that can be quit powerful. This command fully constructs the entire in-memory structures used by `azpbs autoscale` to allow the user to interact with them dynamically. All of the objects are passed in to the local scope, and can be listd by calling `pbsprohelp()`. This is a powerful debugging tool.


```bash
[root@pbsserver ~] azpbs shell
CycleCloud Autoscale Shell
>>> pbsprohelp()
config               - dict representing autoscale configuration.
cli                  - object representing the CLI commands
pbs_env              - object that contains data structures for queues, resources etc
queues               - dict of queue name -> PBSProQueue object
jobs                 - dict of job id -> Autoscale Job
scheduler_nodes      - dict of hostname -> node objects. These represent purely what the scheduler sees without additional booting nodes / information from CycleCloud
resource_definitions - dict of resource name -> PBSProResourceDefinition objects.
default_scheduler    - PBSProScheduler object representing the default scheduler.
pbs_driver           - PBSProDriver object that interacts directly with PBS and implements PBS specific behavior for scalelib.
demand_calc          - ScaleLib DemandCalculator - pseudo-scheduler that determines the what nodes are unnecessary
node_mgr             - ScaleLib NodeManager - interacts with CycleCloud for all node related activities - creation, deletion, limits, buckets etc.
pbsprohelp            - This help function
>>> queues.workq.resources_default
{'place': 'scatter:group=group_id'}
>>> jobs["0"].node_count
2
```

`azpbs shell` can also take in as an argument `--script path/to/python_file.py`, allowing the user to have full access to the in-memory structures, again by passing in the objects through the local scope, to customize the autoscale behavior.

```bash
[root@pbsserver ~] cat example.py 
for bucket in node_mgr.get_buckets():
    print(bucket.nodearray, bucket.vm_size, bucket.available_count)

[root@pbsserver ~] azpbs shell -s example.py 
execute Standard_F2s_v2 50
execute Standard_D2_v4 50
execute Standard_E2s_v4 50
```
## Timeouts
By default we set idle and boot timeouts across all nodes.
```"idle_timeout": 300,
   "boot_timeout": 3600
```
You can also set these per nodearray.
```"idle_timeout": {"default": 300, "nodearray1": 600, "nodearray2": 900},
   "boot_timeout": {"default": 3600, "nodearray1": 7200, "nodearray2": 900},
```
## Logging
By default, `azpbs` will use `/opt/cycle/pbspro/logging.conf`, as defined in `/opt/cycle/pbsspro/autoscale.json`. This will create the following logs.

### /opt/cycle/pbspro/autoscale.log

`autoscale.log` is the main log for all `azpbs` invocations.

### /opt/cycle/pbspro/qcmd.log
`qcmd.log` every PBS executable invocation and the response, so you can see exactly what commands are being run.

### /opt/cycle/pbspro/demand.log
Every `autoscale` iteration, `azpbs` prints out a table of all of the nodes, their resources, their assigned jobs and more. This log
contains these values and nothing else.

## Using Altair PBS Professional in CycleCloud

CycleCloud project for OpenPBS uses opensource version of OpenPBS. You may use your own
[Altair PBS Professional](https://www.altair.com/pbs-professional/) licenses and installers according to your Altair PBS Professional license agreement.  
This section documents how to use Altair PBS Professional with the CycleCloud OpenPBS project.

### Prerequisites

This example will use the 2022.1.1 version, which has been tested with the template.

1. Users must provide Altair PBS Professional binaries (the same works with RHEL 8.x with _.el8.x86_64.rpm_)

  * pbspro-client-2022.1.1.el7.x86_64.rpm
  * pbspro-execution-2022.1.1.el7.x86_64.rpm
  * pbspro-server-2022.1.1.el7.x86_64.rpm

2. A license server reachable from Azure CycleCloud Altair PBS Professional head node and execution nodes

3. (Optional to tune avilable versions) The cyclecloud cli must be configured. Documentation is available [here](https://docs.microsoft.com/en-us/azure/cyclecloud/install-cyclecloud-cli) 


### Copy the binaries into the cloud locker

To copy the installer with _azcopy_ to the Azure CycleCloud storage account, use the following commands (the same works with RHEL 8.x with _.el8.x86_64.rpm_):

```bash

$ azcopy cp pbspro-client-2022.1.1.el7.x86_64.rpm https://<storage-account-name>.blob.core.windows.net/cyclecloud/blobs/pbspro
$ azcopy cp pbspro-execution-2022.1.1.el7.x86_64.rpm https://<storage-account-name>.blob.core.windows.net/cyclecloud/blobs/pbspro
$ azcopy cp pbspro-server-2022.1.1.el7.x86_64.rpm https://<storage-account-name>.blob.core.windows.net/cyclecloud/blobs/pbspro
```

### Define license server

In Altair PBS Professional cluster template, a specific parameter in Advanced Settings allows the definition of license server IP and port.

### Adding other versions to the cluster template

Make a local copy of the Altair PBS Professional template and modify it to use other versions of the installers
instead of the default 2022.1.1.

```bash
wget https://raw.githubusercontent.com/Azure/cyclecloud-pbspro/master/templates/pbspro.txt
```

In the _pbspro.txt_ file, locate the `PBSVersion` definition and
insert the desired version in the options. For example for version 

> NOTE:
> The version should match the one in installer file name.

```ini
        [[[parameter PBSVersion]]]
        Label = Altair PBS Version
        Config.Plugin = pico.form.Dropdown
        Config.Entries := {[Label="Altair PBS Pro 2021.1"; Value="2021.1.4"]}
        DefaultValue = 2021.1.4

```

These configs will make the additional versions available in the UI

### Import the cluster template file

Using the cyclecloud cli, import a cluster template from the new cluster template file.

```bash
cyclecloud import_template -f pbspro.txt --force
```

Similar to this [tutorial](https://docs.microsoft.com/en-us/azure/cyclecloud/tutorials/modify-cluster-template) in the documentation, new Altair PBS Professional cluster is now available in the *Create Cluster* menu in the UI.

Configure and create the cluster in the UI, save it, and start it.

# Contributing

This project welcomes contributions and suggestions.  Most contributions require you to agree to a
Contributor License Agreement (CLA) declaring that you have the right to, and actually do, grant us
the rights to use your contribution. For details, visit https://cla.microsoft.com.

When you submit a pull request, a CLA-bot will automatically determine whether you need to provide
a CLA and decorate the PR appropriately (e.g., label, comment). Simply follow the instructions
provided by the bot. You will only need to do this once across all repos using our CLA.

This project has adopted the [Microsoft Open Source Code of Conduct](https://opensource.microsoft.com/codeofconduct/).
For more information see the [Code of Conduct FAQ](https://opensource.microsoft.com/codeofconduct/faq/) or
contact [opencode@microsoft.com](mailto:opencode@microsoft.com) with any additional questions or comments.
