# StackState Nutanix Agent Check

## Overview

A custom [StackState Agent Check](https://docs.stackstate.com/develop/developer-guides/agent_check/agent_checks) that
makes it possible to integrate [Nutanix Prism](https://www.nutanix.com/uk/products/prism) and 
[Nutanix Karbon](https://www.nutanix.com/uk/products/karbon).

The integration uses the [StackState ETL framework](https://stackstate-lab.github.io/stackstate-etl/) 
to define templates to map Nutanix Rest Api entities to StackState Components, Relations, Events,
Metrics and Health Syncs

See [StackState ETL documentation](https://stackstate-lab.github.io/stackstate-etl/) for more information.

## Installation

From the StackState Agent 2 linux machine, run

```bash 
curl -L https://github.com/stackstate-lab/sts-nutanix-agent-checks/releases/download/v0.1.0/sts_nutanix-0.1.0.zip -o sts_nutanix.zip
tar -xvf sts_nutanix.zip
./install.sh
```

Setup `conf.yaml` on agent machine.

```bash 
cp /etc/stackstate-agent/conf.d/nutanix.d/conf.yaml.example /etc/stackstate-agent/conf.d/nutanix.d/conf.yaml
chown stackstate-agent:stackstate-agent /etc/stackstate-agent/conf.d/nutanix.d/conf.yaml
vi conf.yaml
```

Change the properties to match your environment.

```yaml

init_config:

instances:
  - instance_url: "localvm"
    instance_type: nutanix
    collection_interval: 300
    nutanix:
      url: "https://10.55.90.37:9440"
      prism_central_url: "https://10.55.90.39:9440"
      username: "admin"
      password: "nx2Tech081!"
    domain: "Nutanix"
    layer: "Machines"
    etl:
      refs:
        - "module_dir://sts_nutanix_impl.templates"


```

Run the agent check to verify configured correctly.

```bash
sudo -u stackstate-agent stackstate-agent check nutanix -l info
```

## ETL

Nutanix APIs to syn data from, 

- [PRISM V2.0](https://www.nutanix.dev/api_references/prism-v2-0/#/ZG9jOjQ1Mg-introduction)
- [PRISM CENTRAL V3](https://www.nutanix.dev/api_references/prism-central-v3/#/ZG9jOjQ1Mg-introduction)
- [KARBON](https://www.nutanix.dev/api_references/karbon/#/ZG9jOjQ1Mg-index)


### DataSources


| Name                                                                            | Module                                 | Cls           | Description                       |
|---------------------------------------------------------------------------------|----------------------------------------|---------------|-----------------------------------|
| [nutanix_client](./src/sts_nutanix/sts_nutanix_impl/templates/010_default.yaml) | sts_nutanix_impl.client.nutanix_client | NutanixClient | enables rest calls to Nutanix api |


### Template Mappings

| Name                                                                                                                   | Type                 | 4T          | Nutanix Api                                                                                                            | Description |
|------------------------------------------------------------------------------------------------------------------------|----------------------|-------------|------------------------------------------------------------------------------------------------------------------------|-------------|
| [nutanix_cluster_template](./src/sts_nutanix/sts_nutanix_impl/templates/020_nutanix_clusters.yaml)                     | nutanix-cluster      | Component   | [PrismGateway/services/rest/v2.0/clusters](./tests/resources/responses/get_clusters_v2.json)                           |             |
| [nutanix_rackable_unit_template](./src/sts_nutanix/sts_nutanix_impl/templates/020_nutanix_clusters.yaml)               | nutanix-rack         | Component   | [PrismGateway/services/rest/v2.0/clusters](./tests/resources/responses/get_clusters_v2.json)                           |             |
| [nutanix_host_template](./src/sts_nutanix/sts_nutanix_impl/templates/030_nutanix_hosts.yaml)                           | nutanix-host         | Component   | [api/nutanix/v3/hosts/list](./tests/resources/responses/list_hosts.json)                                               |             |
| [nutanix_disk_template](./src/sts_nutanix/sts_nutanix_impl/templates/032_nutanix_disks.yaml)                           | nutanix-disk         | Component   | [PrismGateway/services/rest/v2.0/disks](./tests/resources/responses/get_disks_v2.json)                                 |             |
| [nutanix_disk_online_template](./src/sts_nutanix/sts_nutanix_impl/templates/032_nutanix_disks.yaml)                    | nutanix-disk         | Health      | [PrismGateway/services/rest/v2.0/disks](./tests/resources/responses/get_disks_v2.json)                                 |             |
| [nutanix_disk_metric_spec_template](./src/sts_nutanix/sts_nutanix_impl/templates/032_nutanix_disks.yaml)               | nutanix-disk         | Metric      | [PrismGateway/services/rest/v2.0/disks](./tests/resources/responses/get_disks_v2.json)                                 |             |
| [nutanix_switch_template](./src/sts_nutanix/sts_nutanix_impl/templates/034_nutanix_networks.yaml)                      | nutanix-vswitch      | Component   | [PrismGateway/services/rest/v2.0/networks](./tests/resources/responses/get_networks_v2.json)                           |             |
| [nutanix_vlan_template](./src/sts_nutanix/sts_nutanix_impl/templates/0034_nutanix_networks.yaml)                       | nutanix-vlan         | Component   | [PrismGateway/services/rest/v2.0/networks](./tests/resources/responses/get_networks_v2.json)                           |             |
| [nutanix_storage_container_template](./src/sts_nutanix/sts_nutanix_impl/templates/036_nutanix_storage_containers.yaml) | nutanix-storage      | Component   | [PrismGateway/services/rest/v2.0/storage_containers](./tests/resources/responses/get_storage_containers_v2.json)       |             |
| [nutanix_vdisk_template](./src/sts_nutanix/sts_nutanix_impl/templates/038_nutanix_vdisks.yaml)                         | nutanix-vdisk        | Component   | [PrismGateway/services/rest/v2.0/vdisks](./tests/resources/responses/get_vdisks_v2.json)                               |             |
| [nutanix_vm_template](./src/sts_nutanix/sts_nutanix_impl/templates/040_nutanix_vms.yaml)                               | nutanix-vm           | Component   | [api/nutanix/v3/vms/list](./tests/resources/responses/listvms.json)                                                    |             |
| [nutanix_vm_disk](./src/sts_nutanix/sts_nutanix_impl/templates/020_nutanix_clusters.yaml)                              | nutanix-vm-disk      | Component   | [api/nutanix/v3/vms/list](./tests/resources/responses/listvms.json)                                                    |             |
| [nutanix_volume_group_template](./src/sts_nutanix/sts_nutanix_impl/templates/050_nutanix_volume_groups.yaml)           | nutanix-volumegroup  | Component   | [PrismGateway/services/rest/v2.0/volume_groups](./tests/resources/responses/get_volumes_groups_v2.json)                |             |
| [karbon_cluster_template](./src/sts_nutanix/sts_nutanix_impl/templates/060_karbon_clusters.yaml)                       | cluster              | Component   | [karbon/v1-beta.1/k8s/clusters](./tests/resources/responses/karbon_list_k8s_clusters.json)                             |             |
| [karbon_cluster_node_template](./src/sts_nutanix/sts_nutanix_impl/templates/070_karbon_cluster_nodes.yaml)             | nutanix-vm           | Component   | [karbon/v1-alpha.1/k8s/clusters/{cluster}/node-pools](./tests/resources/responses/karbon_list_cluster_node_pools.json) |             |
| [karbon_cluster_ahv_config_template](./src/sts_nutanix/sts_nutanix_impl/templates/070_karbon_cluster_nodes.yaml)       | cluster              | Component   | [karbon/v1-alpha.1/k8s/clusters/{cluster}/node-pools](./tests/resources/responses/karbon_list_cluster_node_pools.json) |             |


## Development

StackState Nutanix Agent Check is developed in Python 3, and is transpiled to Python 2.7 during build.

---
### Prerequisites:

- Python v.3.7+. See [Python installation guide](https://docs.python-guide.org/starting/installation/)
- [Poetry](https://python-poetry.org/docs/#installation)
- [Docker](https://www.docker.com/get-started)
- [Custom Synchronization StackPack](https://docs.stackstate.com/stackpacks/integrations/customsync)
---

### Setup local code repository


The poetry install command creates a virtual environment and downloads the required dependencies.

Install the [stsdev](https://github.com/stackstate-lab/stslab-dev) tool into the virtual environment.

```bash 
python -m pip install https://github.com/stackstate-lab/stslab-dev/releases/download/v0.0.7/stslab_dev-0.0.7-py3-none-any.whl
```

Finalize the downloading of the StackState Agent dependencies using `stsdev`

```bash
stsdev update
```
### Prepare local `.env` file

The `.env` file is used by `stsdev` to prepare and run the StackState Agent Docker image. Remember to change the
StackState url and api key for your environment.

```bash

cat <<EOF > ./.env
#STSDEV_IMAGE_EXT=tests/resources/docker/agent_dockerfile
STS_URL=https://xxx.stackstate.io/receiver/stsAgent
STS_API_KEY=xxx
STSDEV_ADDITIONAL_COMMANDS=/etc/stackstate-agent/share/install.sh
STSDEV_ADDITIONAL_COMMANDS_FG=true
EXCLUDE_LIBS=charset-normalizer,stackstate-etl,stackstate-etl-agent-check
EOF
```
### Preparing Agent check conf.yaml

```
cp ./tests/resources/conf.d/nutanix.d/conf.yaml.example ./tests/resources/conf.d/nutanix.d/conf.yaml
```
---

### Running in Intellij

Setup the module sdk to point to the virtual python environment created by Poetry.
Default on macos is `~/Library/Caches/pypoetry/virtualenvs`

Create a python test run config for `tests/test_nutanix_check.py`

You can now run the integration from the test.

---
### Running using `stsdev`

```bash

stsdev agent check nutanix 
```

### Running StackState Agent to send data to StackState

```bash

stsdev agent run
```

---

## Quick-Start for `stsdev`

`stsdev` is a tool to aid with the development StackState Agent integrations.

### Managing dependencies

[Poetry](https://python-poetry.org/) is used as the packaging and dependency management system.

Dependencies for your project can be managed through `poetry add` or `poetry add -D` for development dependency.

```console
$ poetry add PyYAML
```
### Code styling and linting

```console
$ stsdev code-style
```

### Build the project
To build the project,
```console
$ stsdev build --no-run-tests
```
This will automatically run code formatting, linting, tests and finally the build.

### Unit Testing
To run tests in the project,
```console
$ stsdev test
```
This will automatically run code formatting, linting, and tests.

### Dry-run a check

A check can be dry-run inside the StackState Agent by running

```console
$ stsdev agent check nutanix
```
Before running the command, remember to copy the example conf `tests/resources/conf.d/nutanix.d/conf.yaml.example` to
`tests/resources/conf.d/nutanix.d/conf.yaml`.


### Running checks in the Agent

Starts the StackState Agent in the foreground using the test configuration `tests/resources/conf.d`

```console
$ stsdev agent run
```

### Packaging checks

```console
$  stsdev package --no-run-tests
```
This will automatically run code formatting, linting, tests and finally the packaging.
A zip file is created in the `dist` directory.  Copy this to the host running the agent and unzip it.
Run the `install.sh`.

