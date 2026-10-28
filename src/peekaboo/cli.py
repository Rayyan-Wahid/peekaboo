"""Project entry point and local environment checks."""

import argparse
import platform
import shutil

from . import __version__


def main(argv=None):
    parser = argparse.ArgumentParser(description="Peekaboo traffic privacy research prototype")
    parser.add_argument("--version", action="version", version=f"Peekaboo {__version__}")
    commands = parser.add_subparsers(dest="command")
    commands.add_parser("doctor", help="Check external capture and live jitter tools")
    collection = commands.add_parser('collect', help='Collect isolated HTTPS traces through a local tunnel')
    collection.add_argument('--sites', default='configs/sites.csv')
    collection.add_argument('--output', default='data/raw')
    collection.add_argument('--interface', default=r'\Device\NPF_Loopback')
    collection.add_argument('--visits', type=int, default=2)
    collection.add_argument('--seconds', type=int, default=20)
    collection.add_argument('--pause', type=float, default=10)
    collection.add_argument('--seed', type=int, default=42)
    collection.add_argument('--limit', type=int)
    collection.add_argument('--driver', help='Optional explicit chromedriver executable')
    args = parser.parse_args(argv)
    if args.command == 'collect':
        from .collect import collect
        return collect(args)
    if args.command == "doctor":
        from .collect import executable
        print(f"Platform: {platform.system()}")
        for name in ("tshark", "dumpcap", "tc"):
            print(f"{name}: {executable(name) or 'not installed / not on PATH'}")
        print("Live jitter requires Linux and traffic-control permissions.")
        print("Collector implemented; training, defense, and dashboard are planned.")
        return 0
    parser.print_help()
    return 0
