# OpenPLC CLI
> ⚠️ **Warning:**  
> This project is experimental and currently under active testing.  
> Use it **only in safe, non-production environments**.

A command-line interface for OpenPLC.

## Prerequisites

This tool requires `pipx` to be installed.

## Installation

To install the OpenPLC CLI, run the following command:

```bash
pipx install git+https://github.com/CoLorenzo/openplc-cli.git
```

## Usage



The CLI provides the following commands:



- `login`: Authenticates with the OpenPLC instance.

- `device`: Manages Modbus slave devices.

  - `ls`: Lists the configured slave devices.

  - `create`: Creates a new slave device.

- `program`: Manages programs on the PLC.

  - `ls`: Lists the available programs.

  - `create`: Uploads a new program.

- `plc`: Controls the PLC runtime.

  - `start`: Starts the PLC.

  - `stop`: Stops the PLC.



For detailed help on each command, you can use the `--help` flag. For example:



```bash

openplc-cli device --help

```



## Contributing



Contributions are welcome! Please open an issue or submit a pull request.



## License



This project is licensed under the MIT License.


