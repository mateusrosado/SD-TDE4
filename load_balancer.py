from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import threading
import urllib.error
import urllib.request

PORTA_LB = 8080
SERVIDORES = [
    "http://127.0.0.1:8001",
    "http://127.0.0.1:8002",
    "http://127.0.0.1:8003",
]

indice_atual = 0
trava_rr = threading.Lock()


def escolher_servidor_round_robin():
  global indice_atual
  with trava_rr:
    servidor = SERVIDORES[indice_atual]
    indice_atual = (indice_atual + 1) % len(SERVIDORES)
    return servidor


class ServidorBalanceador(ThreadingHTTPServer):
  allow_reuse_address = True
  daemon_threads = True


class ManipuladorBalanceador(BaseHTTPRequestHandler):

  def do_GET(self):
    destino = escolher_servidor_round_robin()
    url_destino = f"{destino}{self.path}"
    porta_destino = destino.split(":")[-1]

    print(
        f"[LB] Repassando requisicao para instancia {porta_destino} |"
        " Algoritmo: RoundRobin",
        flush=True,
    )

    try:
      req = urllib.request.Request(url_destino, method="GET")
      with urllib.request.urlopen(req, timeout=5) as resposta:
        corpo = resposta.read()
        self.send_response(resposta.status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(corpo)))
        self.end_headers()
        self.wfile.write(corpo)
    except Exception as erro:
      erro_json = json.dumps({
          "erro": "Falha ao comunicar com instancia",
          "instancia": destino,
          "detalhe": str(erro),
      }).encode("utf-8")
      self.send_response(502)
      self.send_header("Content-Type", "application/json")
      self.send_header("Content-Length", str(len(erro_json)))
      self.end_headers()
      self.wfile.write(erro_json)

  def log_message(self, format, *args):
    return


if __name__ == "__main__":
  balanceador = ServidorBalanceador(("127.0.0.1", PORTA_LB), ManipuladorBalanceador)
  print(
      f"[LB] Balanceador iniciado em http://127.0.0.1:{PORTA_LB} | Algoritmo:"
      " RoundRobin",
      flush=True,
  )
  try:
    balanceador.serve_forever()
  except KeyboardInterrupt:
    print("\n[LB] Balanceador encerrado.", flush=True)
    balanceador.server_close()