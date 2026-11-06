"""Project entry point and local environment checks."""

import argparse
import platform
from pathlib import Path

from . import __version__


def main(argv=None):
    parser = argparse.ArgumentParser(description="Peekaboo traffic privacy research prototype")
    parser.add_argument("--version", action="version", version=f"Peekaboo {__version__}")
    commands = parser.add_subparsers(dest="command")
    commands.add_parser("doctor", help="Check external capture and live jitter tools")
    extract = commands.add_parser('extract', help='Extract audited capture metadata with fixed date splits')
    extract.add_argument('--root', type=Path, default=Path('.'))
    extract.add_argument('--workers', type=int, default=None)
    experiment = commands.add_parser('experiment', help='Train and evaluate baseline and simulated jitter')
    experiment.add_argument('--root', type=Path, default=Path('.'))
    experiment.add_argument('--run-name', default='experiment-v1')
    predict = commands.add_parser('predict', help='Predict a controlled capture using a local trained model')
    predict.add_argument('capture', type=Path)
    predict.add_argument('--proxy-port', type=int, required=True)
    predict.add_argument('--model', type=Path, required=True)
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
    if args.command == 'extract':
        from .features import extract_dataset
        print(extract_dataset(args.root, args.workers))
        return 0
    if args.command == 'experiment':
        from .experiment import run_experiment
        print(run_experiment(args.root, args.run_name))
        return 0
    if args.command == 'predict':
        import json
        from .experiment import predict_capture
        print(json.dumps(predict_capture(args.capture, args.proxy_port, args.model), indent=2))
        return 0
    if args.command == 'collect':
        from .collect import collect
        return collect(args)
    if args.command == "doctor":
        from .collect import executable
        print(f"Platform: {platform.system()}")
        for name in ("tshark", "dumpcap", "tc"):
            print(f"{name}: {executable(name) or 'not installed / not on PATH'}")
        print("Live jitter requires Linux and traffic-control permissions.")
        print("Use extract, experiment, and predict for the metadata and simulation pipeline.")
        return 0
    parser.print_help()
    return 0
