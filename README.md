# ShopNow - Balanceamento de Carga e Tolerância a Falhas

Implementação prática de escalabilidade horizontal (*Scale-Out*) e alta disponibilidade para o e-commerce **ShopNow**, desenvolvida para a disciplina de Sistemas Distribuídos.

O projeto substitui uma arquitetura monolítica centralizada (ponto único de falha) por um cluster de múltiplas instâncias independentes atrás de um **Balanceador de Carga de Camada 7 (HTTP)**, capaz de distribuir requisições de alta concorrência e realizar *failover* transparente em cenários críticos de tráfego (como a Black Friday).

---

## Arquitetura do Sistema

```text
                        +-----------------------------------+
                        |   Clientes (curl / ab / wrk)      |
                        +-----------------+-----------------+
                                          |
                                 HTTP GET | Porta 8080
                                          v
                        +-----------------------------------+
                        |     Balanceador de Carga (L7)     |
                        |         load_balancer.py          |
                        |   [Round Robin | Least Conn.]     |
                        |   [Health Check Ativo + Retry]    |
                        +----+------------+------------+----+
                             |            |            |
            +----------------+            |            +----------------+
            | HTTP                        | HTTP                        | HTTP
            v                             v                             v
+-----------------------+     +-----------------------+     +-----------------------+
|   Instância ShopNow   |     |   Instância ShopNow   |     |   Instância ShopNow   |
|       server.py       |     |       server.py       |     |       server.py       |
|      Porta: 8001      |     |      Porta: 8002      |     |      Porta: 8003      |
+-----------------------+     +-----------------------+     +-----------------------+
```

### Principais Características Técnicas
- **Zero Dependências Externas:** Construído 100% com a biblioteca padrão do Python 3 (`http.server`, `threading`, `urllib.request`, `json`), rodando nativamente em Windows, Linux e macOS.
- **Concorrência Multi-thread:** Uso de `ThreadingHTTPServer` com fila de *backlog* TCP expandida (`request_queue_size = 512`) e exclusão mútua (`threading.Lock`) para suportar rajadas de conexões simultâneas sem condições de corrida (*race conditions*).
- **Arquitetura Stateless:** As instâncias da ShopNow não retêm estado de sessão localmente, permitindo que qualquer nó processe qualquer requisição ou assuma o tráfego em caso de queda.
- **Health Check Híbrido (Ativo e Passivo):**
  - *Ativo:* Thread em segundo plano consulta periodicamente a rota `/health` de cada servidor a cada `1.5s`, removendo nós defeituosos e reintegrando-os automaticamente assim que se recuperam.
  - *Passivo com Retry:* Se uma instância falhar exatamente no instante de uma compra, o balanceador captura a exceção, isola o nó imediatamente e redireciona a mesma requisição para outra instância saudável sem retornar erro ao cliente final.

---

## Algoritmos de Balanceamento Implementados

1. **Round Robin (`rr`):**
   - **Funcionamento:** Distribui as requisições de forma sequencial e circular entre todas as instâncias saudáveis (`8001 -> 8002 -> 8003 -> 8001`).
   - **Indicação:** Cenários onde todos os servidores possuem capacidade de hardware equivalente e tempo de resposta uniforme.

2. **Least Connections / Menor Número de Conexões Ativas (`lc`):**
   - **Funcionamento:** Monitora em tempo real quantas requisições estão em andamento simultaneamente em cada instância e direciona a nova requisição para o servidor com menos conexões abertas no momento.
   - **Indicação:** Cenários dinâmicos ou assimétricos em que uma instância sofre degradação de performance ou processa tarefas mais demoradas, evitando formação de filas no servidor lento.

---

## Estrutura de Arquivos

- `server.py`: Servidor HTTP das instâncias da loja ShopNow (aceita porta e atraso artificial por argumento de linha de comando).
- `load_balancer.py`: Proxy reverso e balanceador de carga HTTP na porta `8080`.
- `README.md`: Documentação técnica e guia de execução dos testes.

---

## Como Executar o Projeto

Abra **5 terminais** na pasta raiz do projeto:

### 1. Iniciar as 3 Instâncias da ShopNow (Terminais 1, 2 e 3)

```bash
# Terminal 1
python server.py 8001

# Terminal 2
python server.py 8002

# Terminal 3
python server.py 8003
```

> **Dica (Simulação de Lentidão):** Para simular uma instância sobrecarregada (ex: `0.3s` de latência por requisição na porta `8001`), passe o tempo em segundos como segundo argumento:
> ```bash
> python server.py 8001 0.3
> ```

### 2. Iniciar o Balanceador de Carga (Terminal 4)

Para rodar com o algoritmo **Round Robin** (padrão):
```bash
python load_balancer.py rr
```

Para rodar com o algoritmo **Least Connections**:
```bash
python load_balancer.py lc
```

---

## Endpoints Disponíveis

### No Balanceador (`http://127.0.0.1:8080`)
- `GET /comprar` (ou qualquer rota de negócio): Encaminha a requisição para uma instância saudável segundo o algoritmo ativo.
- `GET /status`: Retorna um relatório JSON em tempo real contendo o algoritmo em uso, status de saúde (`ON`/`OFF`) de cada instância, conexões ativas no momento, total de redirecionamentos de *failover* e o placar acumulado de requisições atendidas por porta.

### Direto nas Instâncias (`http://127.0.0.1:8001`, `8002`, `8003`)
- `GET /health`: Retorna HTTP `200` (`saudavel`) ou HTTP `503` (`indisponivel`).
- `GET /simular/queda`: Ativa o modo de falha na instância (passa a recusar requisições com erro `503` sem precisar fechar o terminal).
- `GET /simular/recuperar`: Restaura a instância para o estado saudável (`200`).

---

## Roteiro de Testes e Simulações (Terminal 5)

### Cenário 1: Verificar Distribuição Simétrica (Round Robin)
Com as 3 instâncias sem atraso e o balanceador em modo `rr`, dispare requisições e consulte o placar:

```bash
curl.exe http://127.0.0.1:8080/comprar
curl.exe http://127.0.0.1:8080/status
```

### Cenário 2: Comparar Round Robin vs. Least Connections sob Lentidão
1. Reinicie a instância `8001` com atraso de `0.3s`:
   ```bash
   python server.py 8001 0.3
   ```
2. Inicie o balanceador em modo **Least Connections**:
   ```bash
   python load_balancer.py lc
   ```
3. Dispare uma bateria de requisições concorrentes e consulte `http://127.0.0.1:8080/status`: observe que as instâncias rápidas (`8002` e `8003`) absorvem automaticamente a maior parte do tráfego enquanto a `8001` permanece ocupada.

### Cenário 3: Simulação de Queda de Servidor e Failover Automático
1. Derrube a instância `8002` encerrando o processo com `Ctrl+C` no Terminal 2 **ou** disparando:
   ```bash
   curl.exe http://127.0.0.1:8002/simular/queda
   ```
2. Observe no terminal do balanceador a detecção imediata da queda (`[LB Health] Instancia 8002 OFFLINE`).
3. Continue enviando requisições para `http://127.0.0.1:8080/comprar` e verifique que **nenhuma falha é retornada ao cliente** (o tráfego é dividido entre `8001` e `8003`).
4. Recupere a instância `8002` religando o servidor ou executando:
   ```bash
   curl.exe http://127.0.0.1:8080/simular/recuperar
   ```
5. Em até `1.5s`, o Health Check detecta o retorno (`[LB Health] Instancia 8002 RECUPERADA e reintegrada`) e volta a distribuir carga para ela.

---

## Testes de Carga e Concorrência (`ab` / `wrk` / Python)

### Utilizando Apache Benchmark (`ab`)
Disparo de 1.000 requisições com 50 clientes simultâneos:
```bash
ab -n 1000 -c 50 http://127.0.0.1:8080/comprar
```

*(Caso execute o `ab` de dentro do WSL 2 apontando para o Windows no PowerShell, crie o alias abaixo para mapear o IP da interface virtual automaticamente):*
```powershell
function ab {
    $ipWin = (Get-NetIPConfiguration | Where-Object { $_.IPv4DefaultGateway -ne $null }).IPv4Address.IPAddress | Select-Object -First 1
    $novosArgs = $args | ForEach-Object { $_ -replace "127\.0\.0\.1", $ipWin -replace "localhost", $ipWin }
    wsl ab @novosArgs
}
ab -n 500 -c 30 http://127.0.0.1:8080/comprar
```

### Utilizando `wrk`
Teste contínuo durante 10 segundos utilizando 4 threads e 50 conexões abertas:
```bash
wrk -t4 -c50 -d10s http://127.0.0.1:8080/comprar
```

### Alternativa Nativa em Python (PowerShell / Bash sem ferramentas externas)
Disparo de 300 requisições com 30 threads simultâneas:
```powershell
python -c "import urllib.request; from concurrent.futures import ThreadPoolExecutor; res = list(ThreadPoolExecutor(30).map(lambda _: urllib.request.urlopen('http://127.0.0.1:8080/comprar').status, range(300))); print('Requisicoes 200 OK:', res.count(200))"
```