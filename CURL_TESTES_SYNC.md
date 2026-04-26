# Comandos curl para testar o endpoint sync

## 1) Teste sem autenticacao (esperado: 401)

```bash
curl -i "http://localhost:8000/api/sync?id=des_dr2&pos=CIRCLE%2036.30911%20-10.18749%202&format=fits&band=g"
```

## 2) Obter token de autenticacao

```bash
curl -s -X POST "http://localhost:8000/auth-token/" \
  -H "Content-Type: application/json" \
  -d '{"username":"SEU_USUARIO","password":"SUA_SENHA"}'
```

Saida esperada:

```json
{"token":"..."}
```

## 3) Exportar token em variavel de ambiente

```bash
TOKEN="SEU_TOKEN_AQUI"
```

## 4) Chamar endpoint sync autenticado (caso com possivel retorno 200 ou 422)

```bash
curl -i -G "http://localhost:8000/api/sync" \
  -H "Authorization: Token $TOKEN" \
  --data-urlencode "id=des_dr2" \
  --data-urlencode "pos=CIRCLE 36.30911 -10.18749 2" \
  --data-urlencode "engine=astrocut" \
  --data-urlencode "format=fits" \
  --data-urlencode "band=g"
```

- Se houver todos os arquivos de entrada e o processamento concluir, retorna 200 com arquivo.
- Se faltar algum FITS esperado localmente, retorna 422 com `Input file unavailable`.

## 5) Salvar retorno binario em arquivo local (quando houver 200)

```bash
curl -s -G "http://localhost:8000/api/sync" \
  -H "Authorization: Token $TOKEN" \
  --data-urlencode "id=des_dr2" \
  --data-urlencode "pos=CIRCLE 36.30911 -10.18749 0.01" \
  --data-urlencode "engine=legacy" \
  --data-urlencode "format=fits" \
  --data-urlencode "band=g" \
  -o sync_result_test.fits
```

## 6) Exemplo para validar negação de acesso por policy (esperado: 403)

```bash
curl -i -G "http://localhost:8000/api/sync" \
  -H "Authorization: Token $TOKEN" \
  --data-urlencode "id=private_survey" \
  --data-urlencode "pos=CIRCLE 36.30911 -10.18749 0.01" \
  --data-urlencode "engine=astrocut" \
  --data-urlencode "format=fits" \
  --data-urlencode "band=g"
```

## 7) Fluxo completo em duas linhas (token + teste)

```bash
TOKEN=$(curl -s -X POST "http://localhost:8000/auth-token/" -H "Content-Type: application/json" -d '{"username":"SEU_USUARIO","password":"SUA_SENHA"}' | python -c "import sys,json; print(json.load(sys.stdin)['token'])")
curl -i -G "http://localhost:8000/api/sync" -H "Authorization: Token $TOKEN" --data-urlencode "id=des_dr2" --data-urlencode "pos=CIRCLE 36.30911 -10.18749 0.01" --data-urlencode "engine=astrocut" --data-urlencode "format=fits" --data-urlencode "band=g"
```
