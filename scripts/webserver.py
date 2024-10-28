#!/usr/bin/env python
# Copyright 2021-2024
# Georgia Tech
# All rights reserved
# Do not post or publish in any public or forbidden forums or websites

import http.server
import socketserver
import argparse
import hashlib
import time

parser = argparse.ArgumentParser()
parser.add_argument('--text', default="Default web server")
FLAGS = parser.parse_args()

# generate a sha256 hash of current time
anti_cheating_hash = hashlib.sha256("cs6250{}".format(time.time()).encode()).hexdigest()
with open("/autograder/submission/anti_cheating_hash.txt", "w") as f:
    f.write(anti_cheating_hash)

class Handler(http.server.SimpleHTTPRequestHandler):
    # Disable logging DNS lookups
    def address_string(self):
        return str(self.client_address[0])

    def do_GET(self):
        self.send_response(200)
        self.send_header("Content-type", "text/html")
        self.end_headers()
        self.wfile.write("<h1>{} ({})</h1>\n".format(FLAGS.text, anti_cheating_hash).encode('UTF-8'))
        self.wfile.flush()

PORT = 80
httpd = socketserver.TCPServer(("", PORT), Handler)
httpd.serve_forever()
