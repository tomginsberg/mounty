import argparse
import logging
import os
import select
import socket
import struct
import sys
import threading
import time
import warnings
from typing import List
import requests

from flask import Flask, request, abort
from tqdm import tqdm

try:
    import iterfzf
except ImportError:
    iterfzf = None

DISCOVERY_MCAST_GRP = os.environ.get("DISCOVERY_MCAST_GRP", "239.255.16.27")
DISCOVERY_MCAST_PORT = int(os.environ.get("DISCOVERY_MCAST_PORT", 5008))
DISCOVERY_PORT = int(os.environ.get("DISCOVERY_PORT", 5009))


def discover_devices(timeout=1) -> List[str]:
    devices = []

    # Set up a multicast socket
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM, socket.IPPROTO_UDP)
    sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    sock.bind(('', DISCOVERY_PORT))
    mreq = struct.pack("4sl", socket.inet_aton(DISCOVERY_MCAST_GRP), socket.INADDR_ANY)
    sock.setsockopt(socket.IPPROTO_IP, socket.IP_ADD_MEMBERSHIP, mreq)
    sock.setblocking(0)

    # Send multicast discovery message
    message = b"mounty_discover"
    sock.sendto(message, (DISCOVERY_MCAST_GRP, DISCOVERY_MCAST_PORT))

    # Listen for device responses
    start_time = time.time()
    while time.time() - start_time < timeout:
        ready = select.select([sock], [], [], timeout)
        if ready[0]:
            data, addr = sock.recvfrom(1024)
            if data and data.decode("utf-8").startswith("mounty_here"):
                devices.append(f'{data.decode("utf-8").split(":")[1]} ({addr[0]})')

    sock.close()
    return devices


def multicast_listener():
    # Set up a multicast socket
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM, socket.IPPROTO_UDP)
    sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    sock.bind(('', DISCOVERY_MCAST_PORT))
    mreq = struct.pack("4sl", socket.inet_aton(DISCOVERY_MCAST_GRP), socket.INADDR_ANY)
    sock.setsockopt(socket.IPPROTO_IP, socket.IP_ADD_MEMBERSHIP, mreq)
    device_name = get_device_name()

    while True:
        data, addr = sock.recvfrom(1024)
        if data and data.decode("utf-8") == "mounty_discover":
            response = f"mounty_here:{device_name}".encode("utf-8")
            sock.sendto(response, addr)


def register_device(name, registry_file):
    with open(registry_file, "w") as f:
        f.write(name)

    print(bold_text(f'Device name {colorful_text(name, 33)}'), bold_text(f'has been registered in {registry_file}'))


def get_registry_path():
    return os.environ.get("MOUNTY_REGISTRY", os.path.expanduser("~/.mounty_registry"))


def get_device_name():
    registry_file = get_registry_path()
    if os.path.exists(registry_file):
        with open(registry_file, "r") as f:
            return f.read().strip()
    else:
        return 'unknown device'


def get_local_ip():
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
            s.connect(('10.255.255.255', 1))
            local_ip = s.getsockname()[0]
    except Exception:
        local_ip = '127.0.0.1'
    return local_ip


def select_device() -> str:
    devices = discover_devices()

    if not devices:
        print(f"{bold_text('No devices found running mounty listen.')}")
        return ""

    print(f"{bold_text('Devices running mounty listen:')}")
    for i, device in enumerate(devices):
        print(f"{i + 1}. {device}")

    selected_index = int(input("Select a device by entering its number: ")) - 1
    selected_device = devices[selected_index]

    return selected_device


def colorful_text(text, color_code):
    return f'\033[{color_code}m{text}\033[0m'


def bold_text(text):
    return f'\033[1m{text}\033[0m'


def listen(port=8000, auto_confirm=False):
    app = Flask(__name__)
    app.logger.disabled = True
    log = logging.getLogger("werkzeug")
    log.setLevel(logging.ERROR)

    @app.route("/", methods=["POST"])
    def handle_post():
        if request.method == "POST":
            filename = request.headers.get("X-Filename")
            filesize = request.headers.get("X-Filesize")
            device_name = request.headers.get("X-Device")
            if filename and filesize:
                print(f'{bold_text("Incoming File:")} {colorful_text(filename, 34)}')
                file_size = f'{int(filesize) / 1024 / 1024:.2f} MB'
                print(f'{bold_text("Size:")} {colorful_text(file_size, 34)}')
                print(f'{bold_text("Sender:")} {colorful_text(device_name, 34)}')

                if auto_confirm:
                    confirm = "y"
                else:
                    confirm = input('Would you like to download the file? (y/n) ')

                if confirm.lower() == "y":
                    start_time = time.time()
                    file_data = request.get_data()
                    file_size = len(file_data)

                    if os.path.exists(os.path.basename(filename)):
                        # ask for overwrite
                        overwrite = input(f'{bold_text("File already exists. Would you like to overwrite it? (y/n) ")}')
                        if overwrite.lower() != "y":
                            print(f'{bold_text("File not saved.")}')
                            print(f'\n🔎 {bold_text("Listening on:")} {colorful_text(get_local_ip(), 32)}')
                            return "File not saved", 418

                    with open(os.path.basename(filename), "wb") as f:
                        for chunk in tqdm(
                                (file_data[i: i + 1024] for i in range(0, file_size, 1024)),
                                total=(file_size // 1024) + 1,
                                unit="KB",
                                desc=bold_text("Downloading"),
                        ):
                            f.write(chunk)

                    end_time = time.time()
                    download_time = end_time - start_time
                    print(f"{bold_text('Download time:')} {download_time:.2f} seconds")
                    print(f"{bold_text('Download speed:')} {file_size / download_time / 1024 / 1024:.2f} MB/s")
                    print(f'\n🔎 {bold_text("Listening on:")} {colorful_text(get_local_ip(), 32)}')
                    return "File received", 200
                else:
                    print(f'\n🔎 {bold_text("Listening on:")} {colorful_text(get_local_ip(), 32)}')
                    abort(418)
            else:
                print(f'\n🔎 {bold_text("Listening on:")} {colorful_text(get_local_ip(), 32)}')
                abort(400)

        print(f'\n🔎 {bold_text("Listening on:")} {colorful_text(get_local_ip(), 32)}')
        return "Invalid request", 400

    name = get_device_name()
    if name == 'unknown device':
        warnings.warn(
            f'🗻 {bold_text("Warning:")} '
            f'{colorful_text("Device name is unknown. Please register a device name using mounty register.", 33)}')

    print(f'🗻 {bold_text(f"Mounty user {name} is listening on:")} {colorful_text(get_local_ip(), 32)}')
    # Start the multicast listener in a separate thread
    multicast_thread = threading.Thread(target=multicast_listener, daemon=True)
    multicast_thread.start()
    app.run(host="0.0.0.0", port=port)


def share(filename, port=8000):
    print(f'🗻 {bold_text("Mounty is sharing:")} {colorful_text(filename if filename is not None else "stdin", 32)}')
    if filename is not None and not os.path.exists(filename):
        print(f'{bold_text("Error:")} {colorful_text("File not found.", 31)}')
        sys.exit(1)

    devices = discover_devices()
    if len(devices) == 0:
        print(f'{bold_text("Error:")} {colorful_text("No devices found.", 31)}')
        sys.exit(1)
    elif len(devices) == 1:
        device_spec = devices[0]
    else:
        if iterfzf is not None:
            device_spec = iterfzf.iterfzf(devices)
        else:
            device_spec = select_device()
    target_ip = device_spec.split("(")[1][: -1]

    file_data = None
    if filename is not None:
        filesize = os.path.getsize(filename)
    else:
        file_data = sys.stdin.buffer.read()
        filesize = len(file_data)

    file_size = f'{int(filesize) / 1024 / 1024:.2f} MB'

    print(f'{bold_text("Sharing:")} {colorful_text(filename, 34)}')
    print(f'{bold_text("Size:")} {colorful_text(file_size, 34)}')
    print(f'{bold_text("Sending to:")} {colorful_text(device_spec, 32)}')

    url = f'http://{target_ip}:{port}/'
    try:
        if filename is not None:
            with open(filename, 'rb') as f:
                response = requests.post(url, data=f, headers={
                    "Content-Length": str(filesize),
                    "X-Filename": os.path.basename(filename),
                    "X-Filesize": str(filesize),
                    "X-Device": f'{get_device_name()} ({get_local_ip()})'
                })
        # otherwise read from std in
        else:
            response = requests.post(url, data=file_data, headers={
                "Content-Length": str(len(file_data)),
                "X-Filename": "download",
                "X-Filesize": str(len(file_data)),
                "X-Device": f'{get_device_name()} ({get_local_ip()})'
            })
        print(
            f'{bold_text("Response:")} {colorful_text(response.status_code, 34)} {colorful_text(response.reason, 34)}')
    except Exception as e:
        print(f'{bold_text("Error:")} {colorful_text(str(e), 31)}')


def main():
    parser = argparse.ArgumentParser(description="Mounty: Simple file sharing over local network")
    subparsers = parser.add_subparsers(dest='command', required=True)

    listen_parser = subparsers.add_parser('listen', help='Listen for incoming files')
    listen_parser.add_argument('port', help='Port to Listen On', default=8000, type=int, nargs='?')
    # add a -y commend to auto accept incoming files
    listen_parser.add_argument('-y', '--yes', help='Automatically accept incoming files', action='store_true')

    share_parser = subparsers.add_parser('share', help='Share a file with another device')
    share_parser.add_argument('filename', help='File to share', default=None, nargs='?')
    share_parser.add_argument('port', help='Port to Share On', default=8000, type=int, nargs='?')

    subparsers.add_parser('discover', help='Discover devices on the local network')

    register = subparsers.add_parser('register', help='Register a name for your device')
    register.add_argument('username', help='Username')

    args = parser.parse_args()

    if args.command == 'listen':
        try:
            listen(args.port, auto_confirm=args.yes)
        except KeyboardInterrupt:
            print("\nShutting down...")
            sys.exit(0)
    elif args.command == 'share':
        share(args.filename, port=args.port)
    elif args.command == 'discover':
        devices = discover_devices()
        if len(devices) == 0:
            print(f'{bold_text("No devices found.")}')
        else:
            print(f'{bold_text("Devices:")}')
            for device in devices:
                print(f'  {device}')
    elif args.command == 'register':
        registry_file = get_registry_path()
        register_device(args.username, registry_file)


if __name__ == "__main__":
    main()
