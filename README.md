# StackState Nutanix Agent Check

# Overview

A custom [StackState Agent Check](https://docs.stackstate.com/develop/developer-guides/agent_check/agent_checks) that
makes it possible to integrate Nutanix.

The integration allows a user to setup SL1 queries to fetch devices for an organization(s).
For each device, the user has the ability to define mapping templates that map the device to it's 
StackState component equivalent.  The template mechanism if flexible enough to let users do the mapping declaratively
or fully in code.  Templates and Queries are defined in the `conf.yaml` configuration used by the agent check.


# Sample conf.yaml

Additional sections in this document will address the important parts of the configuration.

```yaml
init_config:

instances:
  - instance_url: "localvm"
    instance_type: sl1check
    collection_interval: 300
    sl1:
      url: "https://10.0.0.12"
      username: "em7admin"
      password: "em7admin"
    domain: "SL1"
    layer: "Device"
    organization_search:
        op: "eq"                 
        value: "StackState"
    queries:
      - name: all
        template_refs:
          - generic_device_template
    template:
      components:
        - name: generic_device_template
          selector: "|True"
          spec:
            name: "$.name"
```

# Organization Search

Used to filter out Organization from the synchronization.

```yaml
...
instances:
  - ...
    ...
    organization_search:
        op: "eq"                 
        value: "StackState"
    ...
```

The `op` property can have one of the following values:

- contains
- beginsWith
- endsWith
- doesNotContain
- doesNotBeginWith
- doesNotEndWith
- in
- notIn
- eq
- neq

When using `in` or `notIn` the `value` property must be a list. 

```yaml
...
    value: ["StackState", "SL1"]
...
```

# Queries

The list of queries are used to fetch sub-sets of devices from SL1

```yaml
...
instances:
  - ...
    ...
    queries:
        - name: cloud_services
          query:
            field: logicalName
            op: "eq"
            value: "AWS Cloud Service"
          template_refs:
            - generic_device_template 
        - name: all
          template_refs:
            - generic_device_template
    ...
```
## Query Properties


| Name          | Type   | Description                                                               | 
|---------------|--------|---------------------------------------------------------------------------|
| name          | string | Name of the query                                                         |
| query         | object | Optional. When left out, all devices are retrieved                        |
| query.field   | string | Device field to match. Options are `logicalName`, `virtualType`, `class`  |
| query.op      | string | Same as `op` describ in Organization Search section                       |
| query.value   | string | Desired device value                                                      |
| template_refs | list   | The templates to be used to process the mapping of each device from query |

## Query Results

A list of devices with the device having the following representation,

```json
[
  {
    "id": "1",
    "ip": "192.158.23.10",
    "componentDescendants": {
      "edges": []
    },
    "alignedAttributes": [],
    "name": "MyLinuxHost",
    "state": "3",
    "events": {
      "edges": [
        {
          "node": {
            "id": "6",
            "severity": "3",
            "message": "Device Failed Availability Check: UDP/SNMP check requested but invalid or no credential was specified."
          }
        }
      ]
    },
    "deviceClass": {
      "logicalName": "Ping ICMP",
      "class": "Ping",
      "virtualType": "physical"
    }
  }
]
```

# Templates

A template can have a declarative nature by declaring the component properties under the `spec` property.
Or the component can be created via code under the `code` property.

```yaml
...
instances:
  - ...
    ...
    template:
      components:
        - name: generic_device_template
          selector: "|True"
          spec:
            name: "$.name"
            type: "|type()"
            layer: "Devices"
            labels: ["staticlabel", "|'label %s' % 'as code'", "$.name"]
        - name: code_template
          selector: "$.deviceClass.logicalName.startswith('AWS')"
          code: |
            component.uid = uid()
            component.set_name(jpath("$.name", device))
            component.set_type(ctype())
            component.properties.add_label_kv("virtualType", device["deviceClass"]["virtualType"])
            
```

## Template Activation

The `selector` property contains an [expression](#Expressions) that resolves to true or false.
When true the template is considered active for the current device and will be applied.


## Component Properties

| Name          | Type   | Description                                                              | 
|---------------|--------|--------------------------------------------------------------------------|
| uid           | string | Optional. Defaults to `urn:sl1:id:/<id>` when not defined                |
| name          | string | Optional. Defaults to device id.                                         |
| layer         | string | Optional. Defaults to default value in conf.yaml                         |
| domain        | string | Optional. Defaults to default value in conf.yaml                         |
| environment   | string | Optional. Defaults to default value in conf.yaml                         |
| labels        | list   | Optional.                                                                |
| identifiers   | list   | Optional. Automatically adds uid                                         |
| processor     | code   | Optional. Process `component` object using code to set other properties  |

## Expressions

The templating mechanism all the used of expressions for property values. 

### JsonPath Expression

Any field value starting with `$.` is assumed to be a Json path.  Using Json path one can extract values from the target
device.  See [Json Path Syntax](https://github.com/h2non/jsonpath-ng#jsonpath-syntax) for more details.

### Code Expression

Any field value starting with `|` is assumed to be a code expression. Any valid python code can be used.
The following can be reference,


| Name      | Type     | Description                                                                                               | 
|-----------|----------|-----------------------------------------------------------------------------------------------------------|
| factory   | object   | See [TopologyFactory](src/sts_nutanix/sts_nutanix_impl/model/factory.py)                                        |
| component | object   | The current component under construction. See [Component](src/sts_nutanix/sts_nutanix_impl/model/stackstate.py) |
| device    | object   | The current device being mapped.                                                                          |
| uid       | function | Generates the default identifier `urn:sl1:id:/<device id>`                                                |
| ctype     | function | Creates the StackState type by using the DeviceClass logical name                                         |
| jpath     | function | Allows for the resolution of a Json path expression. `jpath("$.name", device)`                            |

# Agent Check Installation

These instructions are for the [StackState Agent Linux Installation](https://docs.stackstate.com/setup/agent/linux).

Download SL1 agent check [release](https://github.com/stackstate-lab/sts-sl1-agent-checks/releases/download/v0.1.0/sts_sl1-0.1.0.zip)
to the machine running the StackState Agent.

```bash
$ curl -o sts_sl1-0.1.0.zip -L https://github.com/stackstate-lab/sts-sl1-agent-checks/releases/download/0.1.0/sts_sl1-0.1.0.zip
$ unzip ./sts_sl1-0.1.0.zip
$ ./install.sh
$ cd /etc/stackstate-agent/conf.d/sl1.d
$ cp ./conf.yaml.example ./conf.yaml
$ chown stackstate-agent:stackstate-agent ./conf.yaml
$ vi ./conf.yaml
```

Change the configuration to match your environment. Example,

```yaml
init_config:

instances:
  - instance_url: "localvm"
    instance_type: sl1check
    collection_interval: 300
    sl1:
      url: "https://10.0.0.12"
      username: "em7admin"
      password: "em7admin"

```

On the StackState server create an instance of the Custom Synchronization StackPack for the `instance_url` and 
`instance_type=sl1check`.

# Development

---
## Prerequisites:

- Python v.3.7+. See [Python installation guide](https://docs.python-guide.org/starting/installation/)
- [Poetry](https://python-poetry.org/docs/#installation)
- [Docker](https://www.docker.com/get-started)
- [Custom Synchronization StackPack](https://docs.stackstate.com/stackpacks/integrations/customsync)
---
## Setup
### Setup local code repository

```bash 
git clone git@github.com:stackstate-lab/sts-sl1-agent-checks.git
cd ./sts-sl1-agent-checks
poetry install 
```

The poetry install command creates a virtual environment and downloads the required dependencies.

Install the [stsdev](https://github.com/stackstate-lab/stslab-dev) tool into the virtual environment.

```bash 
python -m pip install https://github.com/stackstate-lab/stslab-dev/releases/download/v0.0.4/stslab_dev-0.0.4-py3-none-any.whl
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
STS_URL=https://k8sdemo.demo.stackstate.io/receiver/stsAgent
STS_API_KEY=xxxx
EOF
```

### Preparing Agent check conf.yaml

```
cp ./tests/resources/conf.d/sl1.d/conf.yaml.example ./tests/resources/conf.d/sl1.d/conf.yaml
```
Edit the conf.yaml to resemble the following.

```yaml
init_config:

instances:
  - instance_url: "localvm"
    instance_type: sl1check
    collection_interval: 300
    sl1:
      url: "https://10.0.0.12"
      username: "em7admin"
      password: "em7admin"
```
---
## Running in Intellij

Setup the module sdk to point to the virtual python environment created by Poetry.
Default on macos is `~/Library/Caches/pypoetry/virtualenvs`

Create a python test run config for `sl1-agent-checks/tests/test_sl1_check.py`

Edit `sl1-agent-checks/tests/test_sl1_check.py` to point to your conf.yaml and not the `conf.yaml.example`

You can now run the integration from the test.

## Running using `stsdev`

```bash

stsdev agent check sl1 
```

## Running StackState Agent to send data to StackState

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
$ stsdev agent check rongen
```
Before running the command, remember to copy the example conf `tests/resources/conf.d/rontgen.d/conf.yaml.example` to
`tests/resources/conf.d/rontgen.d/conf.yaml`.


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

