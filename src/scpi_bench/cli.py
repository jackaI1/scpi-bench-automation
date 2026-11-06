"""Command-line interface; exit 0 pass, 1 limit failure, 2 error, 130 interrupted."""
import argparse
import threading

from .bench import SimBench
from .runner import run_soak, run_sweep
from .server import running_server


def parser():
    root = argparse.ArgumentParser(description='Run a simulated instrument bench')
    commands = root.add_subparsers(dest='command', required=True)
    sweep = commands.add_parser('sweep', help='sweep supply voltage and check readings')
    sweep.add_argument('--voltages', type=float, nargs='+', default=[0, 1, 2, 3, 4, 5])
    sweep.add_argument('--tolerance', type=float, default=0.11, help='absolute error limit in V')
    sweep.add_argument('--settle', type=float, default=0, help='seconds after setting each voltage')
    soak = commands.add_parser('soak', help='sample a simulated thermal profile until a trip')
    soak.add_argument('--temperatures', type=float, nargs='+', default=[25, 30, 35])
    soak.add_argument('--low', type=float, default=20, help='inclusive lower temperature in C')
    soak.add_argument('--high', type=float, default=60, help='inclusive upper temperature in C')
    soak.add_argument('--voltage', type=float, default=3.3)
    soak.add_argument('--interval', type=float, default=0, help='seconds between temperature readings')
    for item in (sweep, soak):
        item.add_argument('--output', default='reports', help='parent directory for unique run folders')
    server = commands.add_parser('serve', help='bridge one simulated instrument to a local TCP socket')
    server.add_argument('--instrument', choices=['supply', 'dmm', 'scope'], default='supply')
    server.add_argument('--port', type=int, default=5025, help='TCP port; 0 chooses an unused port')
    return root


def main(argv=None):
    arguments = parser()
    args = vars(arguments.parse_args(argv))
    command = args.pop('command')
    try:
        with SimBench() as bench:
            if command == 'serve':
                if not 0 <= args['port'] <= 65535:
                    raise ValueError('port must be between 0 and 65535')
                with running_server(bench, **args):
                    threading.Event().wait()
                return 0
            root = args.pop('output')
            result = (run_sweep if command == 'sweep' else run_soak)(bench, root, **args)
            print(f'{result.status}: {result.path / "report.html"}')
            return {'PASS': 0, 'FAIL': 1, 'ERROR': 2}[result.status]
    except KeyboardInterrupt:
        print('Interrupted; supply shutdown requested.')
        return 130
    except (ValueError, OSError) as error:
        arguments.exit(2, f'error: {error}\n')
