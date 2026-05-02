"""
Tiny mock SOAP server for the SoapDetector. Implements a single
``getRunState`` operation returning a ``runState`` string. The state can
be toggled at runtime via ``GET /set?state=stopped``.

Pure-stdlib (no ``spyne`` dependency) — we hand-roll the SOAP envelope
because the contract is one method with one string field.
"""
from __future__ import annotations

import argparse
from http.server import BaseHTTPRequestHandler, HTTPServer
from urllib.parse import parse_qs, urlparse

WSDL = """<?xml version="1.0"?>
<definitions name="RunControl"
  targetNamespace="http://example.org/runctrl"
  xmlns:tns="http://example.org/runctrl"
  xmlns:xsd="http://www.w3.org/2001/XMLSchema"
  xmlns:soap="http://schemas.xmlsoap.org/wsdl/soap/"
  xmlns="http://schemas.xmlsoap.org/wsdl/">
  <message name="getRunStateRequest"/>
  <message name="getRunStateResponse">
    <part name="runState" type="xsd:string"/>
  </message>
  <portType name="RunControlPort">
    <operation name="getRunState">
      <input message="tns:getRunStateRequest"/>
      <output message="tns:getRunStateResponse"/>
    </operation>
  </portType>
  <binding name="RunControlBinding" type="tns:RunControlPort">
    <soap:binding style="rpc" transport="http://schemas.xmlsoap.org/soap/http"/>
    <operation name="getRunState">
      <soap:operation soapAction="getRunState"/>
      <input><soap:body use="literal" namespace="http://example.org/runctrl"/></input>
      <output><soap:body use="literal" namespace="http://example.org/runctrl"/></output>
    </operation>
  </binding>
  <service name="RunControlService">
    <port name="RunControlPort" binding="tns:RunControlBinding">
      <soap:address location="http://{host}:{port}/RunControl"/>
    </port>
  </service>
</definitions>"""

ENVELOPE = """<?xml version="1.0"?>
<soap:Envelope xmlns:soap="http://schemas.xmlsoap.org/soap/envelope/"
               xmlns:tns="http://example.org/runctrl">
  <soap:Body>
    <tns:getRunStateResponse>
      <runState>{state}</runState>
    </tns:getRunStateResponse>
  </soap:Body>
</soap:Envelope>"""


class _State:
    value = "Running"


def _make_handler(host: str, port: int):
    class Handler(BaseHTTPRequestHandler):
        def log_message(self, fmt, *args):  # quiet
            return

        def do_GET(self):  # noqa: N802
            url = urlparse(self.path)
            if url.path == "/set":
                qs = parse_qs(url.query)
                new = qs.get("state", [""])[0]
                if new:
                    _State.value = new
                self._send(200, "text/plain", f"state={_State.value}\n".encode())
                return
            if url.path.endswith("?wsdl") or url.query == "wsdl":
                self._send(200, "text/xml",
                           WSDL.format(host=host, port=port).encode())
                return
            self._send(200, "text/plain",
                       f"runState={_State.value}\n".encode())

        def do_POST(self):  # noqa: N802
            length = int(self.headers.get("Content-Length", "0"))
            _ = self.rfile.read(length)
            self._send(200, "text/xml",
                       ENVELOPE.format(state=_State.value).encode())

        def _send(self, code: int, ctype: str, body: bytes) -> None:
            self.send_response(code)
            self.send_header("Content-Type", ctype)
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

    return Handler


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description="Mock SOAP server for SoapDetector")
    p.add_argument("--host", default="127.0.0.1")
    p.add_argument("--port", type=int, default=8080)
    p.add_argument("--state", default="Running",
                   help="initial runState (e.g. Running, Stopped)")
    args = p.parse_args(argv)

    _State.value = args.state
    server = HTTPServer((args.host, args.port), _make_handler(args.host, args.port))
    print(
        f"SOAP server on http://{args.host}:{args.port}/RunControl?wsdl  "
        f"(initial state={_State.value})\n"
        f"Toggle: curl 'http://{args.host}:{args.port}/set?state=Stopped'"
    )
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
