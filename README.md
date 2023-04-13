# 🗻 mounty

Local network file sharing made easy !

## Install

```bash
pip install git+https://github.com/tomginsberg/mounty.git
```

## Usage

```bash
# Receiver
⟩ mounty listen
# Sender
⟩ mounty share <file>
```

## Help

```bash
mounty -h
```
```bash
usage: mounty [-h] {listen,share,discover} ...

Mounty: Simple file sharing over local network

positional arguments:
  {listen,share,discover}
    listen              Listen for incoming files
    share               Share a file with another device
    discover            Discover devices on the local network

options:
  -h, --help            show this help message and exit
```