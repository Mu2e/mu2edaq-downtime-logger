# Diagnostic tools

Each script emits the kind of message its corresponding detector consumes,
so you can verify a deployment end-to-end without needing the live DAQ.
All tools are run as Python modules from the project root with the venv active.

```bash
source venv/bin/activate
```

## zmq_publish — ZmqDetector simulator

Binds a ZMQ PUB socket and publishes state messages or heartbeats.

```bash
# Publish "running" every second.
python -m tools.zmq_publish --endpoint tcp://*:5555 --state running --interval 1

# Send a one-shot "stopped" and exit.
python -m tools.zmq_publish --endpoint tcp://*:5555 --state stopped --once

# Custom message body.
python -m tools.zmq_publish --endpoint tcp://*:5555 --message "my custom payload"
```

Options: `--endpoint` (default `tcp://*:5555`), `--topic` (default empty),
`--state {running,stopped,heartbeat}`, `--interval SECS`, `--once`, `--message TEXT`

## udp_broadcast — UdpDetector simulator

Sends UDP datagrams to a host or broadcast address.

```bash
# Broadcast "running" every second on the local network.
python -m tools.udp_broadcast --host 255.255.255.255 --port 9000 --state running

# Send once to a specific host.
python -m tools.udp_broadcast --host 127.0.0.1 --port 9000 --state stopped --once
```

Options: `--host` (default `255.255.255.255`), `--port` (default `9000`),
`--state {running,stopped,heartbeat}`, `--interval SECS`, `--once`, `--message TEXT`

## soap_server — SoapDetector simulator

Runs a minimal HTTP/SOAP server that responds to `getRunState` requests.
Toggle the run state at runtime with a plain HTTP GET.

```bash
# Start with initial state "Running".
python -m tools.soap_server --host 127.0.0.1 --port 8080 --state Running

# In another terminal, flip the state:
curl 'http://127.0.0.1:8080/set?state=Stopped'
curl 'http://127.0.0.1:8080/set?state=Running'
```

WSDL: `http://127.0.0.1:8080/RunControl?wsdl`

Options: `--host` (default `127.0.0.1`), `--port` (default `8080`),
`--state TEXT` (default `Running`)

## disk_writer — DiskActivityDetector simulator

Periodically touches a file inside a watched directory.

```bash
# Touch /data/raw/.heartbeat every 5 seconds.
python -m tools.disk_writer --path /data/raw --interval 5

# Write once and exit.
python -m tools.disk_writer --path /tmp/daq-test --once

# Use a custom filename.
python -m tools.disk_writer --path /tmp/daq-test --filename daq.touch --interval 2
```

Options: `--path DIR` (required), `--interval SECS` (default `5`),
`--filename NAME` (default `.heartbeat`), `--once`

## log_writer — LogfileDetector simulator

Appends timestamped lines to a log file matching the detector's regex patterns.

```bash
# Write "RUN STOPPED" once.
python -m tools.log_writer --path /var/log/artdaq/run.log --message "RUN STOPPED"

# Write "RUN STARTED" three times, one per second.
python -m tools.log_writer --path /var/log/artdaq/run.log \
    --message "RUN STARTED" --count 3 --interval 1
```

Options: `--path FILE` (required), `--message TEXT` (required),
`--count N` (default `1`), `--interval SECS` (default `1`)

## Typical local test workflow

```bash
# Terminal 1 — start the application
./start-mu2edaq-downtime-logger.sh --foreground

# Terminal 2 — simulate a DAQ heartbeat (keeps UdpDetector UP)
python -m tools.udp_broadcast --host 127.0.0.1 --port 9000 --state running

# Terminal 3 — simulate disk activity (keeps DiskActivityDetector UP)
python -m tools.disk_writer --path /tmp/daq-test --interval 5

# To trigger a downtime: stop the heartbeat (Ctrl-C in Terminal 2)
# To recover: restart the heartbeat
```
