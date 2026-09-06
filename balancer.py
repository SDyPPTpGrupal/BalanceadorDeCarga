"""
Balanceador de Carga Casero (Esqueleto inicial)
Sistemas Distribuidos y Programación Paralela - UNLu
"""

import http.server
import socketserver
import os
import sys

PORT = int(os.environ.get("PORT", 80))

class LoadBalancerHandler(http.server.BaseHTTPRequestHandler):
    def do_GET(self):
        # Placeholder: Aquí se implementará la conmutación/redirección de peticiones a los backends
        self.send_response(200)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.end_headers()
        response_body = (
            '{"status": "ok", "message": "Balanceador de carga operativo (esqueleto inicial)"}\n'
        )
        self.wfile.write(response_body.encode("utf-8"))

    def do_POST(self):
        self.do_GET()

def run():
    print(f"[*] Iniciando balanceador de carga en el puerto {PORT}...", flush=True)
    with socketserver.TCPServer(("", PORT), LoadBalancerHandler) as httpd:
        print(f"[*] Escuchando peticiones HTTP en el puerto {PORT}...", flush=True)
        try:
            httpd.serve_forever()
        except KeyboardInterrupt:
            print("\n[*] Apagando balanceador...", flush=True)
            httpd.server_close()
            sys.exit(0)

if __name__ == "__main__":
    run()
