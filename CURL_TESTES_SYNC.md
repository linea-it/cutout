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

## 4) Chamar endpoint sync autenticado (engine astrocut)

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

## 5) Chamar endpoint sync autenticado (engine legacy)

```bash
curl -i -G "http://localhost:8000/api/sync" \
  -H "Authorization: Token $TOKEN" \
  --data-urlencode "id=des_dr2" \
  --data-urlencode "pos=CIRCLE 36.30911 -10.18749 0.01" \
  --data-urlencode "engine=legacy" \
  --data-urlencode "format=fits" \
  --data-urlencode "band=g"
```

## 6) Salvar retorno binario em arquivo local (quando houver 200)

```bash
curl -s -G "http://localhost:8000/api/sync" \
  -H "Authorization: Token $TOKEN" \
  --data-urlencode "id=des_dr2" \
  --data-urlencode "pos=CIRCLE 36.30911 -10.18749 0.01" \
  --data-urlencode "engine=astrocut" \
  --data-urlencode "format=fits" \
  --data-urlencode "band=g" \
  -o sync_result_test.fits
```

## 7) Exemplo para validar negacao de acesso por policy (esperado: 403)

```bash
curl -i -G "http://localhost:8000/api/sync" \
  -H "Authorization: Token $TOKEN" \
  --data-urlencode "id=private_survey" \
  --data-urlencode "pos=CIRCLE 36.30911 -10.18749 0.01" \
  --data-urlencode "engine=astrocut" \
  --data-urlencode "format=fits" \
  --data-urlencode "band=g"
```

```bash
curl -i -G "http://localhost:80/api/sync" \
  -H "Authorization: Token 89cce9976177ed2c275b75782290faa915089518" \
  --data-urlencode "id=des_dr2" \
  --data-urlencode "pos=CIRCLE 36.30911 -10.18749 2" \
  --data-urlencode "engine=astrocut" \
  --data-urlencode "format=png" \
  --data-urlencode "band=gri"
-o sync_result_test.png
```


## 8) Fluxo completo em duas linhas (token + teste)

```bash
TOKEN=$(curl -s -X POST "http://localhost:8000/auth-token/" -H "Content-Type: application/json" -d '{"username":"SEU_USUARIO","password":"SUA_SENHA"}' | python -c "import sys,json; print(json.load(sys.stdin)['token'])")
curl -i -G "http://localhost:8000/api/sync" -H "Authorization: Token $TOKEN" --data-urlencode "id=des_dr2" --data-urlencode "pos=CIRCLE 36.30911 -10.18749 0.01" --data-urlencode "engine=astrocut" --data-urlencode "format=fits" --data-urlencode "band=g"
```

## 9) Ajustar ownership de arquivo gerado no container

Quando o arquivo de saida for criado dentro do container com owner `root:root`, ajuste para uid/gid do host:

```bash
docker compose exec django sudo chown 1000:1000 /data/results/teste.fits
```

Para verificar:

```bash
docker compose exec django ls -l /data/results/teste.fits
```

Coordenadas de exemplo:  cutout/lib/des_cutout.py

```python
if __name__ == "__main__":
    cutouts = [
        {"ra": 36.30911, "dec": -10.18749, "size": 2.0, "band": "g", "format": "fits"},  # 1 - Tile
        {"ra": 36.30911, "dec": -10.18749, "size": 2.0, "band": "gri", "format": "png"},  # 1 - Tile
        {"ra": 36.15801, "dec": -10.33579, "size": 2.0, "band": "g", "format": "fits"},  # 2 - Tile
        {"ra": 36.15801, "dec": -10.33579, "size": 2.0, "band": "gri", "format": "png"},  # 2 - Tile
        # {"ra": 35.23676, "dec": -10.33269, "size": 10.0, "band": "g", "format": "fits"},  # 3 - Tile
    ]

    dc = DesCutout()

    for c in cutouts:
        if c["format"] == "fits":
            filename = "{:.5f}_{:.5f}_{}.fits".format(round(c["ra"], 5), round(c["dec"], 5), c["band"])
            resultfile = Path("/data/results").joinpath(filename)

            result = dc.single_cutout_fits(
                ra=c["ra"], dec=c["dec"], size_arcmin=c["size"], band=c["band"], path=resultfile
            )
            print(result)

        if c["format"] == "png":
            filename = "{:.5f}_{:.5f}.png".format(round(c["ra"], 5), round(c["dec"], 5))
            resultfile = Path("/data/results").joinpath(filename)

            result = dc.single_cutout_png(
                ra=c["ra"], dec=c["dec"], size_arcmin=c["size"], band=c["band"], path=resultfile
            )
            print(result)
```
