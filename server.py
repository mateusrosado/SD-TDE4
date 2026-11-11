import sys
import json
import time
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

porta_instancia = int(sys.argv[1]) if len(sys.argv) > 1 else 8001
atraso_segundos = float(sys.argv[2]) if len(sys.argv) > 2 else 0.0
contador_requisicoes = 0
em_falha = False
trava_estado = threading.Lock()


class ServidorShopNow(ThreadingHTTPServer):
    allow_reuse_address = True
    daemon_threads = True
    request_queue_size = 512


class ManipuladorShopNow(BaseHTTPRequestHandler):

    def enviar_json(self, status_code, dados):
        corpo = json.dumps(dados).encode("utf-8")
        self.send_response(status_code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(corpo)))
        self.send_header("Connection", "close")
        self.end_headers()
        self.wfile.write(corpo)

    def do_GET(self):
        global contador_requisicoes, em_falha

        if self.path == "/health":
            with trava_estado:
                falha_atual = em_falha
            if falha_atual:
                self.enviar_json(503, {"status": "indisponivel", "porta": porta_instancia})
            else:
                self.enviar_json(200, {"status": "saudavel", "porta": porta_instancia})
            return

        if self.path == "/simular/queda":
            with trava_estado:
                em_falha = True
            print(f"[ShopNow {porta_instancia}] ALERTA: Modo de falha ativado.", flush=True)
            self.enviar_json(200, {"instancia": porta_instancia, "simulacao": "queda_ativada"})
            return

        if self.path == "/simular/recuperar":
            with trava_estado:
                em_falha = False
            print(f"[ShopNow {porta_instancia}] INFO: Instancia recuperada e operacional.", flush=True)
            self.enviar_json(200, {"instancia": porta_instancia, "simulacao": "recuperada"})
            return

        with trava_estado:
            if em_falha:
                self.enviar_json(503, {"erro": "Servidor fora do ar", "porta": porta_instancia})
                return
            contador_requisicoes += 1
            numero_atual = contador_requisicoes

        if atraso_segundos > 0:
            time.sleep(atraso_segundos)

        resposta = {
            "loja": "ShopNow",
            "instancia": f"0.0.0.0:{porta_instancia}",
            "porta": porta_instancia,
            "requisicao_instancia": numero_atual,
            "atraso_simulado_s": atraso_segundos,
            "rota": self.path,
            "status": "processado"
        }

        self.enviar_json(200, resposta)

        if numero_atual <= 20 or numero_atual % 50 == 0:
            print(
                f"[ShopNow {porta_instancia}] Requisicao {numero_atual} atendida | "
                f"Tempo: {atraso_segundos}s | Rota: {self.path}",
                flush=True
            )

    def log_message(self, format, *args):
        return


if __name__ == "__main__":
    servidor = ServidorShopNow(("0.0.0.0", porta_instancia), ManipuladorShopNow)
    print(
        f"[ShopNow] Instancia iniciada em http://0.0.0.0:{porta_instancia} | "
        f"Atraso: {atraso_segundos}s",
        flush=True
    )
    try:
        servidor.serve_forever()
    except KeyboardInterrupt:
        print(f"\n[ShopNow {porta_instancia}] Instancia encerrada.", flush=True)
        servidor.server_close()