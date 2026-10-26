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
    args = parser.parse_args(argv)
    if args.command == "doctor":
        print(f"Platform: {platform.system()}")
        for name in ("tshark", "tc"):
            print(f"{name}: {shutil.which(name) or 'not installed / not on PATH'}")
        print("Live jitter requires Linux and traffic-control permissions.")
        print("Status: scaffold only; collection, training, defense, and dashboard are planned.")
        return 0
    parser.print_help()
    return 0
