# 🗻 mounty

Local network file sharing made easy !

## Install

```bash
pip install git+https://github.com/tomginsberg/mounty.git
```

## Usage

*Receiver*

```bash
> mounty listen                                                                                                                                                               ─╯
🗻 Mounty is listening on: 192.168.4.27
```

*Sender*

```bash
> mounty share headshot.png
🗻 Mounty is sharing: headshot.png
Sharing: dark_figure.png
Size: 0.60 MB
Sending to: 192.168.4.27 (only device available)
```

*Receiver*

```bash
Incoming File: headshot.png
Size: 0.60 MB
Source IP: 192.168.4.27
Would you like to download the file? (y/n) <user enters y>
Downloading: 100%|██████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████| 612/612 [00:00<00:00, 237084.52KB/s]
Download time: 0.03 seconds
Download speed: 18.37 MB/s

🔎 Listening on: 192.168.4.27
```

*Sender*

```bash
Response: 200 OK
```