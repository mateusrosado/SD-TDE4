import sys
import json
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

porta_instancia = int(sys.argv[1]) if len(sys.argv) > 1 else 8001
contador_requisicoes = 0
trava_contador = threading.Lock()


class ServidorShopNow(ThreadingHTTPServer):
  allow_reuse_address = True
  daemon_threads = True


class ManipuladorShopNow(BaseHTTPRequestHandler):

  def do_GET(self):
    global contador_requisicoes
    with trava_contador:
      contador_requisicoes += 1
      numero_atual = contador_requisicoes

    resposta = {
        "loja": "ShopNow",
        "instancia": f"127.0.0.1:{porta_instancia}",
        "porta": porta_instancia,
        "requisicao_instancia": numero_atual,
        "rota": self.path,
        "status": "processado",
    }

    corpo = json.dumps(resposta).encode("utf-8")
    self.send_response(200)
    self.send_header("Content-Type", "application/json")
    self.send_header("Content-Length", str(len(corpo)))
    self.end_headers()
    self.wfile.write(corpo)

    print(
        f"[ShopNow {porta_instancia}] Requisicao #{numero_atual} atendida |"
        f" Rota: {self.path}",
        flush=True,
    )

  def log_message(self, format, *args):
    return


if __name__ == "__main__":
  servidor = ServidorShopNow(("127.0.0.1", porta_instancia), ManipuladorShopNow)
  print(
      f"[ShopNow] Instancia iniciada em http://127.0.0.1:{porta_instancia}",
      flush=True,
  )
  try:
    servidor.serve_forever()
  except KeyboardInterrupt:
    print(f"\n[ShopNow {porta_instancia}] Instancia encerrada.", flush=True)
    servidor.server_close()