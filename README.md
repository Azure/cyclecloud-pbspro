# Azure CycleCloud PBS Professional project

PBS Professional is a highly configurable open source workload manager. See the
[PBSPro project site](http://www.pbspro.org/) for an overview and the [PBSpro
documentation](https://www.pbsworks.com/PBSProductGT.aspx?n=Altair-PBS-Professional&c=Overview-and-Capabilities&d=Altair-PBS-Professional,-Documentation)
for more information on using, configuring, and troubleshooting PBS Professional
in general.

Azure CycleCloud uses the open source community edition of PBS Professional.

## Autoscale and scalesets

In order to try and ensure that the correct VMs are provisioned for different types of jobs, CycleCloud treats autoscale of MPI and serial jobs differently in PBS Professional clusters. 

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
