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

## Autoscale and scalesets

In order to try and ensure that the correct VMs are provisioned for different types of jobs, CycleCloud treats autoscale of MPI and serial jobs differently in OpenPBS clusters. 

For serial jobs, multiple VM scalesets (VMSS) are used in order to scale as quickly as possible. For MPI jobs to use the InfiniBand fabric for those instances that support it, all of the nodes allocated to the job have to be deployed in the same VMSS. Currently, a single VMSS is used for all MPI jobs. This can occasionally lead to slower provisioning and deprovisioning of nodes since VMSS operations are atomic. If the scaleset is waiting on some nodes to deprovision, CycleCloud must wait for that operation to complete to provision more nodes.


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
