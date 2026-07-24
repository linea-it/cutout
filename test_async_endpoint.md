# 1. Obter o token com usuário/senha
TOKEN=$(curl -s -X POST "http://localhost:80/auth-token/" \
  -d "username=gverde&password=adminadmin" | python3 -c "import sys,json; print(json.load(sys.stdin)['token'])")

# 2. Submeter o job async (PNG colorido gri, CIRCLE 0.75 2.867 0.033333)
curl -s -X POST "http://localhost:80/api/async" \
  -H "Authorization: Token ${TOKEN}" \
  -H "Content-Type: application/x-www-form-urlencoded" \
  -d "POS=CIRCLE 0.75 2.867 0.033333&format=png&color=true&rgb_bands=gri&id=des_dr2&phase=RUN"
# → retorna JSON com "job_id" e "phase":"QUEUED"

# 3. Consultar a fase (repita até COMPLETED) — troque 154 pelo job_id retornado
curl -s "http://localhost:80/api/async/154/phase" -H "Authorization: Token ${TOKEN}"

# 4. Listar os resultados
curl -s "http://localhost:80/api/async/154/results" -H "Authorization: Token ${TOKEN}"

# 5. Baixar o PNG (result_id vem da listagem acima)
curl -s -o cutout_rgb.png \
  "http://localhost:80/api/async/154/results/job_154_des_dr2_astrocut_rgb_1" \
  -H "Authorization: Token ${TOKEN}"

Observações:

- No POST via form-urlencoded os espaços do POS podem ir literais (o curl codifica); só use %20 se passar na query string de um GET.
- O passo 3 devolve texto puro (QUEUED/EXECUTING/COMPLETED/ERROR). No teste que rodei o job completou em menos de 2 segundos.
- Para um exemplo de erro registrado no banco, use uma região fora do footprint (ex.: POS=CIRCLE 10.0 10.0 0.016667&band=r&format=fits) — a fase termina em ERROR e a mensagem fica no error_message da task.
