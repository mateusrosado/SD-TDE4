import sys
import json
import threading
import urllib.request
import urllib.error
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

PORTA_LB = 8080
SERVIDORES = [
    "http://127.0.0.1:8001",
    "http://127.0.0.1:8002",
    "http://127.0.0.1:8003"
]

algoritmo_arg = sys.argv[1].lower() if len(sys.argv) > 1 else "rr"
ALGORITMO = "LeastConnections" if algoritmo_arg == "lc" else "RoundRobin"

indice_atual = 0
trava_lb = threading.Lock()
conexoes_ativas = {servidor: 0 for servidor in SERVIDORES}
total_atendidas = {servidor: 0 for servidor in SERVIDORES}


def formatar_metricas(dicionario):
    partes = [f"{s.split(':')[-1]}:{v}" for s, v in dicionario.items()]
    return " ".join(partes)


def adquirir_servidor():
    global indice_atual
    with trava_lb:
        total_servidores = len(SERVIDORES)
        if ALGORITMO == "RoundRobin":
            escolhido = SERVIDORES[indice_atual]
            indice_atual = (indice_atual + 1) % total_servidores
        else:
            menor_carga = None
            escolhido = None
            for i in range(total_servidores):
                candidato = SERVIDORES[(indice_atual + i) % total_servidores]
                carga = conexoes_ativas[candidato]
                if menor_carga is None or carga < menor_carga:
                    menor_carga = carga
                    escolhido = candidato
            indice_atual = (SERVIDORES.index(escolhido) + 1) % total_servidores

        conexoes_ativas[escolhido] += 1
        total_atendidas[escolhido] += 1
        ativas_snapshot = formatar_metricas(conexoes_ativas)
        total_snapshot = formatar_metricas(total_atendidas)
        return escolhido, ativas_snapshot, total_snapshot


def liberar_servidor(servidor):
    with trava_lb:
        if conexoes_ativas[servidor] > 0:
            conexoes_ativas[servidor] -= 1


class ServidorBalanceador(ThreadingHTTPServer):
    allow_reuse_address = True
    daemon_threads = True


class ManipuladorBalanceador(BaseHTTPRequestHandler):

    def do_GET(self):
        destino, ativas_str, total_str = adquirir_servidor()
        url_destino = f"{destino}{self.path}"
        porta_destino = destino.split(":")[-1]

        print(
            f"[LB] Destino: {porta_destino} | Algoritmo: {ALGORITMO} | "
            f"Ativas: [{ativas_str}] | Acumulado: [{total_str}]",
            flush=True
        )

        try:
            req = urllib.request.Request(url_destino, method="GET")
            with urllib.request.urlopen(req, timeout=10) as resposta:
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
                "detalhe": str(erro)
            }).encode("utf-8")
            self.send_response(502)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(erro_json)))
            self.end_headers()
            self.wfile.write(erro_json)
        finally:
            liberar_servidor(destino)

    def log_message(self, format, *args):
        return


if __name__ == "__main__":
    balanceador = ServidorBalanceador(("127.0.0.1", PORTA_LB), ManipuladorBalanceador)
    print(
        f"[LB] Balanceador iniciado em http://127.0.0.1:{PORTA_LB} | "
        f"Algoritmo: {ALGORITMO}",
        flush=True
    )
    try:
        balanceador.serve_forever()
    except KeyboardInterrupt:
        print("\n[LB] Balanceador encerrado.", flush=True)
        balanceador.server_close()