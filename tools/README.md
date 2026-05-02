# Diagnostic tools

Each script emits the kind of message its corresponding detector consumes,
so you can verify a deployment end-to-end without needing the live DAQ.

```bash
# ZMQ publisher: send "running" every second to whoever subscribes.
python -m tools.zmq_publish --endpoint tcp://*:5555 --state running --interval 1

# Send a one-shot stop, then exit.
python -m tools.zmq_publish --endpoint tcp://*:5555 --state stopped --once

# UDP broadcaster (defaults to 255.255.255.255:9000).
python -m tools.udp_broadcast --port 9000 --state running --interval 1

# Mock SOAP server. Toggle state with HTTP GETs to /set?state=stopped.
python -m tools.soap_server --port 8080 --state running

# Touch files inside a directory to keep DiskActivityDetector happy.
python -m tools.disk_writer --path /data/raw --interval 5

# Drop lines into a log file. Choose patterns that match your config.
python -m tools.log_writer --path /var/log/artdaq/run.log --message "RUN STOPPED"
```

All five tools share a ``--state {running,stopped}`` flag where applicable
and produce text that matches the default token sets used by the detectors.
