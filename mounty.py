import argparse
import logging
import os
import select
import socket
import struct
import sys
import threading
import time
from typing import List
import requests

from flask import Flask, request, abort
from tqdm import tqdm

try:
    import iterfzf
except ImportError:
    iterfzf = None

ERROR = 0
MCAST_GRP = "224.1.1.1"
MCAST_PORT = 5007
DISCOVERY_MCAST_GRP = "224.1.1.2"
DISCOVERY_MCAST_PORT = 5008
DISCOVERY_PORT = 5009


def discover_devices(timeout=1) -> List[str]:
    devices = []

    # Set up a multicast socket
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM, socket.IPPROTO_UDP)
    sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    sock.bind(('', DISCOVERY_PORT))  # Update this line
    mreq = struct.pack("4sl", socket.inet_aton(DISCOVERY_MCAST_GRP), socket.INADDR_ANY)
    sock.setsockopt(socket.IPPROTO_IP, socket.IP_ADD_MEMBERSHIP, mreq)
    sock.setblocking(0)

    # Send multicast discovery message
    message = b"mounty_discover"
    sock.sendto(message, (DISCOVERY_MCAST_GRP, DISCOVERY_MCAST_PORT))  # Update this line

    # Listen for device responses
    start_time = time.time()
    while time.time() - start_time < timeout:
        ready = select.select([sock], [], [], timeout)
        if ready[0]:
            data, addr = sock.recvfrom(1024)
            if data and data.decode("utf-8") == "mounty_here":
                devices.append(addr[0])

    sock.close()
    return devices


def multicast_listener():
    # Set up a multicast socket
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM, socket.IPPROTO_UDP)
    sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    sock.bind(('', DISCOVERY_MCAST_PORT))  # Update this line
    mreq = struct.pack("4sl", socket.inet_aton(DISCOVERY_MCAST_GRP), socket.INADDR_ANY)
    sock.setsockopt(socket.IPPROTO_IP, socket.IP_ADD_MEMBERSHIP, mreq)

    while True:
        data, addr = sock.recvfrom(1024)
        if data and data.decode("utf-8") == "mounty_discover":
            response = b"mounty_here"
            sock.sendto(response, addr)


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
    log = logging.getLogger("werkzeug")
    log.setLevel(logging.ERROR)

    @app.route("/", methods=["POST"])
    def handle_post():
        if request.method == "POST":
            filename = request.headers.get("X-Filename")
            filesize = request.headers.get("X-Filesize")
            if filename and filesize:
                print(f'{bold_text("Incoming File:")} {colorful_text(filename, 34)}')
                file_size = f'{int(filesize) / 1024 / 1024:.2f} MB'
                print(f'{bold_text("Size:")} {colorful_text(file_size, 34)}')
                print(f'{bold_text("Source IP:")} {colorful_text(request.remote_addr, 34)}')

                if auto_confirm:
                    confirm = "y"
                else:
                    confirm = input('Would you like to download the file? (y/n) ')

                if confirm.lower() == "y":
                    start_time = time.time()
                    file_data = request.get_data()
                    file_size = len(file_data)

                    with open(filename, "wb") as f:
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
                    abort(403)
            else:
                print(f'\n🔎 {bold_text("Listening on:")} {colorful_text(get_local_ip(), 32)}')
                abort(400)

        print(f'\n🔎 {bold_text("Listening on:")} {colorful_text(get_local_ip(), 32)}')
        return "Invalid request", 400

    print(f'🗻 {bold_text("Mounty is listening on:")} {colorful_text(get_local_ip(), 32)}')
    # Start the multicast listener in a separate thread
    multicast_thread = threading.Thread(target=multicast_listener, daemon=True)
    multicast_thread.start()
    app.run(host="0.0.0.0", port=port)


def share(filename, target_ip=None, port=8000):
    print(f'🗻 {bold_text("Mounty is sharing:")} {colorful_text(filename, 32)}')
    if not os.path.exists(filename):
        print(f'{bold_text("Error:")} {colorful_text("File not found.", 31)}')
        sys.exit(1)
    if target_ip is None:
        devices = discover_devices()
        if len(devices) == 0:
            print(f'{bold_text("Error:")} {colorful_text("No devices found.", 31)}')
            sys.exit(1)
        elif len(devices) == 1:
            target_ip = devices[0]
        else:
            if iterfzf is not None:
                target_ip = iterfzf.iterfzf(devices)
            else:
                target_ip = select_device()

    filesize = os.path.getsize(filename)
    file_size = f'{int(filesize) / 1024 / 1024:.2f} MB'

    print(f'{bold_text("Sharing:")} {colorful_text(filename, 34)}')
    print(f'{bold_text("Size:")} {colorful_text(file_size, 34)}')
    print(f'{bold_text("Sending to:")} {colorful_text(target_ip, 32)}')

    url = f'http://{target_ip}:{port}/'
    try:
        with open(filename, 'rb') as f:
            response = requests.post(url, data=f, headers={
                "Content-Length": str(filesize),
                "X-Filename": filename,
                "X-Filesize": str(filesize),
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
    share_parser.add_argument('filename', help='File to share')
    share_parser.add_argument('target_ip', help='Target IP address', default=None, nargs='?')
    share_parser.add_argument('port', help='Port to Share On', default=8000, type=int, nargs='?')

    subparsers.add_parser('discover', help='Discover devices on the local network')

    args = parser.parse_args()

    if args.command == 'listen':
        try:
            listen(args.port, auto_confirm=args.yes)
        except KeyboardInterrupt:
            print("\nShutting down...")
            sys.exit(0)
    elif args.command == 'share':
        share(args.filename, args.target_ip)
    elif args.command == 'discover':
        devices = discover_devices()
        if len(devices) == 0:
            print(f'{bold_text("No devices found.")}')
        else:
            print(f'{bold_text("Devices:")}')
            for device in devices:
                print(f'  {device}')


if __name__ == "__main__":
    main()
