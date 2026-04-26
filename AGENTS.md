# AGENTS

Instrucoes globais para agentes que atuam neste repositorio.

## Escopo

Estas regras valem para todos os agentes (Codex, Claude e similares) durante analise, implementacao, testes e manutencao.

## Regra principal: tudo em container

- Execute comandos de aplicacao somente dentro de containers Docker.
- Use `docker compose -f local.yml exec` para comandos em servicos ja em execucao.
- Use `docker compose -f local.yml run --rm` para comandos one-shot quando o servico nao precisa ficar ativo.
- Nao execute `python`, `pip`, `pytest`, `mypy`, `flake8`, `black`, `isort`, `pre-commit`, `celery` diretamente no host.

## Proibicao de dependencias no host

- Nunca instalar dependencias Python no host.
- Nunca usar `pip install` no host.
- Toda dependencia nova deve ser declarada em `requirements/*.txt` e instalada via rebuild de imagem.

Fluxo obrigatorio para novas dependencias:
1. Editar arquivo de requirements apropriado.
2. Rebuild de imagem do servico.
3. Subir/reiniciar containers.
4. Validar com testes/lint dentro do container.

## Comandos permitidos no host

No host, apenas comandos de orquestracao e apoio:
- `docker compose ...`
- `just ...`
- `git ...`

## Padrao de execucao

Assuma `local.yml` como compose padrao de desenvolvimento.

Exemplos:

Subir ambiente:
- `docker compose -f local.yml up -d --build`

Parar ambiente:
- `docker compose -f local.yml down --remove-orphans`

Entrar no app:
- `docker compose -f local.yml exec django bash`

Comando Django:
- `docker compose -f local.yml exec django python manage.py migrate`

Rodar testes:
- `docker compose -f local.yml exec django pytest`

Rodar lint:
- `docker compose -f local.yml exec django black --check .`
- `docker compose -f local.yml exec django isort --check-only .`
- `docker compose -f local.yml exec django flake8`
- `docker compose -f local.yml exec django mypy cutout`

Executar comando one-shot:
- `docker compose -f local.yml run --rm django python manage.py shell`

Logs:
- `docker compose -f local.yml logs -f --tail=200 django`
- `docker compose -f local.yml logs -f --tail=200 celeryworker`

## Uso de justfile

O `justfile` e o caminho preferencial para operacao diaria.
Quando usar `just`, os comandos internos devem continuar sendo executados via containers.

Comandos recomendados:
- `just check-auth`
- `just up`
- `just ps`
- `just logs-f`
- `just test`
- `just lint`
- `just down`

## Implementacao planejada (cutout sync)

Para as proximas fases de codigo:
- Manter suporte a `CIRCLE`, `RANGE` e `POLYGON` no endpoint sync.
- Aplicar camada de policy antes de discovery/cutout.
- Considerar DES DR2 como publico na policy inicial (retorno verdadeiro).
- Preservar arquitetura modular: API -> Policy -> Discovery -> Engine -> Task.

## Checklist obrigatorio antes de concluir alteracoes

1. Containers necessarios estao ativos.
2. Migracoes aplicadas (se houver mudanca de modelo).
3. Testes executados dentro do container.
4. Lint executado dentro do container.
5. Nenhuma dependencia foi instalada no host.
