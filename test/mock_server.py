#!/usr/bin/env python3
"""Tiny local mock of the EC2 instance metadata service plus an HTTP sink.

usage: mock_server.py PORT_FILE REQUEST_LOG MODE
  MODE v2      IMDSv2 only (document requires a valid token)
  MODE v1      IMDSv1 only (token endpoint answers 404, document needs no token)
  MODE hang    every request sleeps 5 s (simulates a stuck metadata service)
  MODE sink    like v2, POST /sink is accepted and recorded

Every request is appended to REQUEST_LOG as one line: METHOD PATH token=yes|no [X-Test=...] [body]
Binds 127.0.0.1 on a random port and writes it to PORT_FILE.
"""
import http.server
import sys
import time

PORT_FILE, REQ_LOG, MODE = sys.argv[1:4]
TOKEN = "mock-token-1234"
DOC = """{
  "accountId" : "123456789012",
  "architecture" : "x86_64",
  "availabilityZone" : "us-east-1b",
  "imageId" : "ami-0abc1234def567890",
  "instanceId" : "i-0123456789abcdef0",
  "instanceType" : "c7g.xlarge",
  "privateIp" : "10.0.1.23",
  "region" : "us-east-1",
  "version" : "2017-09-30"
}
"""


class H(http.server.BaseHTTPRequestHandler):
    def log_message(self, *a):
        pass

    def _rec(self, extra=""):
        tok = "yes" if self.headers.get("X-aws-ec2-metadata-token") == TOKEN else "no"
        with open(REQ_LOG, "a") as f:
            f.write("%s %s token=%s %s\n" % (self.command, self.path, tok, extra))

    def _send(self, code, body=b""):
        self.send_response(code)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_PUT(self):
        self._rec()
        if MODE == "hang":
            time.sleep(5)
        if self.path == "/latest/api/token" and MODE != "v1":
            self._send(200, TOKEN.encode())
        else:
            self._send(404)

    def do_GET(self):
        self._rec()
        if MODE == "hang":
            time.sleep(5)
        ok = self.path == "/latest/dynamic/instance-identity/document"
        authed = self.headers.get("X-aws-ec2-metadata-token") == TOKEN
        if ok and ((MODE == "v1") or authed):
            self._send(200, DOC.encode())
        else:
            self._send(401 if ok else 404)

    def do_POST(self):
        n = int(self.headers.get("Content-Length", 0))
        body = self.rfile.read(n).decode()
        self._rec("X-Test=%s body=%s" % (self.headers.get("X-Test"), body))
        if MODE == "hang":
            time.sleep(5)
        self._send(200)


srv = http.server.ThreadingHTTPServer(("127.0.0.1", 0), H)
with open(PORT_FILE + ".tmp", "w") as f:
    f.write(str(srv.server_address[1]))
import os
os.rename(PORT_FILE + ".tmp", PORT_FILE)
srv.serve_forever()
