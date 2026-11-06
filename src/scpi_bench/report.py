"""Incremental CSV evidence and a self-contained HTML summary for each run."""
import csv
from dataclasses import dataclass
from datetime import datetime, timezone
from html import escape
import json
from pathlib import Path
from uuid import uuid4

from .bench import utc_now

FIELDS = ['timestamp_utc', 'elapsed_s', 'set_voltage_v', 'dmm_v', 'scope_v',
          'frequency_hz', 'temperature_c', 'status']


@dataclass(frozen=True)
class RunResult:
    path: Path
    status: str


class Report:
    def __init__(self, root, kind, settings):
        stamp = datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S.%fZ')
        self.path = Path(root) / f'{stamp}-{kind}-{uuid4().hex[:8]}'
        self.path.mkdir(parents=True, exist_ok=False)
        self.metadata = dict(kind=kind, started_utc=utc_now(), settings=settings,
                             backend='pyvisa-sim', instruments={}, status='ERROR',
                             error='', shutdown_verified=False)
        self.rows = []

    def append(self, row):
        # Flush each sample to disk, preserving partial evidence on interruption.
        with (self.path / 'measurements.csv').open('a', newline='') as stream:
            writer = csv.DictWriter(stream, fieldnames=FIELDS)
            if not self.rows:
                writer.writeheader()
            writer.writerow(row)
        self.rows.append(row)

    def finish(self, status, error, transcript, shutdown_verified):
        self.metadata.update(status=status, error=error, finished_utc=utc_now(),
                             samples=len(self.rows), shutdown_verified=shutdown_verified)
        if not self.rows:
            with (self.path / 'measurements.csv').open('w', newline='') as stream:
                csv.DictWriter(stream, fieldnames=FIELDS).writeheader()
        with (self.path / 'scpi.csv').open('w', newline='') as stream:
            writer = csv.DictWriter(stream, fieldnames=[
                'timestamp_utc', 'instrument', 'command', 'response'])
            writer.writeheader()
            writer.writerows(transcript)
        (self.path / 'run.json').write_text(json.dumps(self.metadata, indent=2) + '\n')
        columns = [key for key in FIELDS if any(key in row for row in self.rows)]
        headings = ''.join(f'<th scope="col">{escape(key)}</th>' for key in columns)
        rows = ''.join('<tr>' + ''.join(f'<td>{escape(str(row.get(key, "")))}</td>'
                                      for key in columns) + '</tr>' for row in self.rows)
        settings = escape(json.dumps(self.metadata, indent=2))
        html = f'''<!doctype html>
<html lang="en"><meta charset="utf-8"><meta name="viewport" content="width=device-width">
<title>Simulated bench {escape(status)}</title>
<style>body{{font:16px system-ui;margin:2rem;color:#152c35;background:#fafafa}}
table{{border-collapse:collapse}}th,td{{border:1px solid #abb;padding:.5rem;text-align:left}}
pre{{white-space:pre-wrap}}.scroll{{overflow-x:auto}}</style>
<h1>Simulated bench: {escape(status)}</h1>
<p>{len(self.rows)} samples. Supply shutdown verified: {shutdown_verified}.</p>
<p>{escape(error)}</p><div class="scroll"><table><thead><tr>{headings}</tr></thead>
<tbody>{rows}</tbody></table></div>
<h2>Run details</h2><pre>{settings}</pre>
<p>These readings came from software simulators, not physical equipment.</p></html>'''
        (self.path / 'report.html').write_text(html)
        return RunResult(self.path, status)
