# Installing the SRE clients 

This section described how to install and use the SightHouse plugins made for the 
different Software Reverse Engineering (SRE) tools.

## Ghidra 

<div markdown="span" style="float:right;margin-left:20px;margin-top:-90px;">

  ![](../assets/images/ghidra-logo.png){ width="120" }

</div>

In order to run the SightHouse plugin, you will need at least [Ghidra 11.3](https://github.com/NationalSecurityAgency/ghidra/releases/tag/Ghidra_11.3_build)
as it now come with Python 3 support thought pyGhidra. 

We advise you to launch for a first time ghidra before installed this plugin.

To install the Ghidra plugin use the following commands:
```bash
git clone https://github.com/quarkslab/sighthouse
cd sighthouse/sighthouse-client
# Deactivate previous virtual env
deactivate 
# Install script
yes | GHIDRA_INSTALL_DIR=/path/to/ghidra make install_ghidra 
```

The script will search for pyGhidra virtual environment, install SightHouse 
client dependencies and then ask you where you want to copy your script.  


## IDA 

<div markdown="span" style="float:right;margin-left:20px;margin-top:-90px;">

  ![](../assets/images/ida-logo.png){ width="120" }

</div>

To install the IDA plugin use the following commands:
```bash
git clone https://github.com/quarkslab/sighthouse
cd sighthouse/sighthouse-client
# Install script
IDA_DIR=/path/to/ida_dir make install_ida 
```

## Binary Ninja

<div markdown="span" style="float:right;margin-left:20px;margin-top:-90px;">

  ![](../assets/images/binja-logo.png){ width="120" }

</div>

To install the Binary Ninja plugin use the following commands:
```bash
git clone https://github.com/quarkslab/sighthouse
cd sighthouse/sighthouse-client
# Install script
make install_binja 
```

After restarting Binary Ninja, there should be a new entry inside the plugins list.

