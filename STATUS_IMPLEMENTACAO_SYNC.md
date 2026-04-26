# Status de Implementacao - Sync Cutout

Data de inicio: 2026-04-26
Escopo: acompanhar implementacao incremental do endpoint sync conforme plano IVOA/DES.
Publico: humanos e agentes de AI.

## Como usar este arquivo

Atualize este documento a cada fase implementada, sempre antes de abrir PR ou seguir para a fase seguinte.

Checklist de atualizacao:
1. Resumo do que foi implementado.
2. Arquivos criados/alterados.
3. Regras de negocio adicionadas ou alteradas.
4. Decisoes tecnicas tomadas.
5. Comandos de validacao executados e resultado.
6. Commit(s) associado(s).

## Estado atual por fase

- Fase 0 (hardening): parcial
- Fase 1 (discovery desacoplado): concluida
- Fase 1.5 (policy de acesso por survey): concluida
- Fase 2 (orquestracao sync via celery): concluida
- Fase 3 (adapter de engine): concluida
- Fase 3.1 (astrocut nativo com discovery DES): concluida
- Fase 4 (descoberta VO remota): adiada (decisao de arquitetura pendente)

## Regras de negocio vigentes

1. Tipos espaciais aceitos no parse: CIRCLE, RANGE, POLYGON.
2. Discovery v1 usa intersecao por bounding box do stencil com tiles DES em CSV.
3. Survey suportado no discovery atual: des_dr2.
4. Se nenhum arquivo for encontrado para a regiao solicitada, o fluxo falha explicitamente com erro de parametro.
5. Camada de policy de survey roda antes do discovery.
6. Policy inicial libera des_dr2 e nega surveys nao reconhecidos.
7. Durante execucao da task, se o arquivo esperado nao estiver acessivel no disco local, a API retorna erro explicito de arquivo indisponivel.
8. A API aceita selecao de engine via parametro `engine`.
9. Engine default atual: `astrocut`.
10. Engine legado permanece disponivel via `engine=legacy`.
11. Discovery de arquivos permanece no backend DES/CSV nesta etapa (sem SIA/TAP por enquanto).

## Decisoes tecnicas registradas

1. Manter abordagem geometrica simples (bounding box) nesta etapa e deixar refinamento cientifico para revisao posterior.
2. Estruturar policy de acesso com interface separada para permitir evolucao futura para surveys privados.
3. Validar cada fase dentro de container antes de commit.
4. Trabalhar em fases pequenas: implementar, testar, validar, commit.
5. Durante fase de aprovacao, manter multiplas ferramentas de cutout ativas para comparacao controlada.
6. Adiar integracao SIA/TAP ate definicao arquitetural formal; manter estabilidade com discovery DES local.

## Historico de implementacao

### Entrada 2026-04-26 - Fase 1

Resumo:
- Criado modulo de discovery desacoplado.
- Implementado locator DES por CSV com suporte a CIRCLE, RANGE e POLYGON.
- Integrado locator no fluxo de dispatch do policy.
- Ajustada task para receber lista de arquivos descobertos.
- Adicionado erro explicito quando nao ha arquivos para a regiao.

Arquivos criados:
- cutout/service/discovery/__init__.py
- cutout/service/discovery/base.py
- cutout/service/discovery/models.py
- cutout/service/discovery/des_csv_locator.py
- cutout/service/discovery/tests/test_des_csv_locator.py

Arquivos alterados:
- cutout/service/policy.py
- cutout/service/tasks.py

Validacao executada:
- docker compose exec django black --check cutout/service/discovery cutout/service/policy.py cutout/service/tasks.py
- docker compose exec django isort --check-only cutout/service/discovery cutout/service/policy.py cutout/service/tasks.py
- docker compose exec django pytest cutout/service/discovery/tests/test_des_csv_locator.py -q
- Resultado: 5 passed

Commit:
- b2edcfb - feat(discovery): add DES CSV locator and integrate dispatch file lookup

### Entrada 2026-04-26 - Fase 1.5

Resumo:
- Criada camada de policy de acesso por survey.
- Implementada policy inicial publica para DES DR2.
- Integrada validacao de acesso antes do discovery no fluxo de dispatch.
- Confirmado comportamento de negacao para survey nao permitido.

Arquivos criados:
- cutout/service/policies/__init__.py
- cutout/service/policies/base.py
- cutout/service/policies/des_public.py
- cutout/service/policies/tests/test_des_public_policy.py

Arquivos alterados:
- cutout/service/policy.py

Validacao executada:
- docker compose exec django black --check cutout/service/policies cutout/service/policy.py
- docker compose exec django isort --check-only cutout/service/policies cutout/service/policy.py
- docker compose exec django pytest cutout/service/policies/tests/test_des_public_policy.py cutout/service/discovery/tests/test_des_csv_locator.py -q
- Resultado: 7 passed

Smoke test de autorizacao:
- Requisicao com id=private_survey em /api/sync
- Resultado observado: 403 com mensagem de acesso negado

Commit:
- b332e38 - feat(policy): add survey access layer before discovery dispatch

## Proxima fase planejada

Fase 3 - Adapter de engine de cutout

Objetivos imediatos:
1. Introduzir interface de engine para desacoplar a API do backend de recorte.
2. Adaptar implementacao atual (DES) para o contrato novo sem quebrar endpoint sync.
3. Preparar ponto de troca para Astrocut em configuracao futura.

### Entrada 2026-04-26 - Preparacao da Fase 3

Resumo:
- Criado esqueleto do modulo `cutout_engine` para iniciar a separacao entre orquestracao e motor de recorte.
- Adicionada interface `CutoutEngine` e implementacoes iniciais para DES e Astrocut (stub).
- Incluido teste unitario basico para validar delegacao do adapter DES para a classe de cutout existente.

Arquivos criados:
- cutout/service/cutout_engine/__init__.py
- cutout/service/cutout_engine/base.py
- cutout/service/cutout_engine/des_engine.py
- cutout/service/cutout_engine/astrocut_engine.py
- cutout/service/cutout_engine/tests/test_des_engine.py

Status:
- Preparacao inicial concluida.
- Integracao do adapter no fluxo principal sera feita na execucao completa da Fase 3.

### Entrada 2026-04-26 - Fase 2

Resumo:
- Endpoint sync passou a aguardar o resultado real da task Celery no fluxo sincrono.
- JobService passou a registrar transicoes de fase EXECUTING, COMPLETED e ERROR.
- Task de cutout passou a validar explicitamente a disponibilidade dos arquivos de entrada.
- Em caso de arquivo de entrada ausente/inacessivel, a API retorna erro explicito (422) com detalhe dos caminhos faltantes.
- Endpoint passou a retornar arquivo via FileResponse quando o resultado existe, com timeout configurado e erro 503 para indisponibilidade do servico.

Arquivos criados:
- cutout/service/tests/test_tasks.py

Arquivos alterados:
- cutout/service/api/views.py
- cutout/service/policy.py
- cutout/service/tasks.py
- cutout/service/uws/service.py
- cutout/service/uws/exceptions.py
- cutout/lib/cutout.py
- .gitignore

Validacao executada:
- docker compose exec django black --check cutout/service/api/views.py cutout/service/policy.py cutout/service/tasks.py cutout/service/uws/service.py cutout/service/uws/exceptions.py cutout/lib/cutout.py cutout/service/tests/test_tasks.py
- docker compose exec django isort --check-only cutout/service/api/views.py cutout/service/policy.py cutout/service/tasks.py cutout/service/uws/service.py cutout/service/uws/exceptions.py cutout/lib/cutout.py cutout/service/tests/test_tasks.py
- docker compose exec django pytest cutout/service/tests/test_tasks.py cutout/service/policies/tests/test_des_public_policy.py cutout/service/discovery/tests/test_des_csv_locator.py -q
- Resultado: 10 passed

Smoke test relevante:
- Requisicao em /api/sync com des_dr2 e coordenada valida no catalogo, mas sem arquivo FITS correspondente local.
- Resultado observado: 422 com mensagem Input file unavailable e lista de arquivos ausentes.

Status:
- Fase 2 finalizada no codigo.
- Comportamento de erro para indisponibilidade de arquivo local validado conforme requisito de ambiente de testes parcial.

### Entrada 2026-04-26 - Fase 3

Resumo:
- Integrada camada de selecao de engine no pipeline de cutout.
- Implementado factory para escolha de backend por nome de engine.
- Mantida ferramenta antiga funcional como opcao (`legacy`).
- Definido `astrocut` como default da API.
- Nesta fase, `astrocut` usa fallback controlado para engine legado para manter operacao funcional durante aprovacao.

Arquivos criados:
- cutout/service/cutout_engine/factory.py
- cutout/service/cutout_engine/tests/test_factory.py
- cutout/service/cutout_engine/tests/test_astrocut_engine.py
- cutout/service/tests/test_cutout_parameters.py

Arquivos alterados:
- cutout/service/api/views.py
- cutout/service/cutout_engine/__init__.py
- cutout/service/cutout_engine/astrocut_engine.py
- cutout/service/cutout_parameters.py
- cutout/service/policy.py
- cutout/service/tasks.py
- test_sync_endpoint.py
- CURL_TESTES_SYNC.md

Validacao executada:
- docker compose exec django black --check cutout/service/api/views.py cutout/service/cutout_parameters.py cutout/service/policy.py cutout/service/tasks.py cutout/service/cutout_engine test_sync_endpoint.py
- docker compose exec django isort --check-only cutout/service/api/views.py cutout/service/cutout_parameters.py cutout/service/policy.py cutout/service/tasks.py cutout/service/cutout_engine test_sync_endpoint.py
- docker compose exec django pytest cutout/service/cutout_engine/tests/test_des_engine.py cutout/service/cutout_engine/tests/test_factory.py cutout/service/cutout_engine/tests/test_astrocut_engine.py cutout/service/tests/test_tasks.py cutout/service/tests/test_cutout_parameters.py -q
- Resultado: 10 passed

Smoke test relevante:
- `engine=legacy` em `/api/sync`: status 200 (streaming)
- `engine=astrocut` em `/api/sync`: status 200 (streaming)

Status:
- Fase 3 finalizada para aprovacao funcional com duas opcoes de ferramenta.
- Integracao nativa do astrocut permanece como evolucao da fase seguinte.

### Entrada 2026-04-26 - Checkpoint de compatibilidade de dependencias

Resumo:
- Validada compatibilidade do ambiente com novas versoes cientificas.
- Confirmado funcionamento do modo legado DES apos upgrade.

Dependencias em runtime (container django):
- numpy 2.4.4
- astropy 7.2.0
- astrocut 1.2.0

Validacao executada:
- docker compose exec django pytest cutout/service/tests/test_tasks.py cutout/service/discovery/tests/test_des_csv_locator.py cutout/service/cutout_engine/tests/test_des_engine.py -q
- docker compose exec django python manage.py shell -c "... engine=legacy ..."
- Resultado: testes verdes e endpoint sync legacy retornando 200 (streaming, application/fits)

### Entrada 2026-04-26 - Fase 3.1 (Astrocut nativo com discovery DES)

Resumo:
- Removido fallback `astrocut -> legacy` no engine Astrocut.
- Integrada chamada nativa ao `astrocut.fits_cut` para pedidos `CIRCLE` em `fits`.
- Mantida descoberta de arquivos no locator DES/CSV atual (sem SIA nesta fase).
- Task passou a repassar a lista de arquivos de entrada para o engine selecionado.

Arquivos alterados:
- cutout/service/cutout_engine/base.py
- cutout/service/cutout_engine/des_engine.py
- cutout/service/cutout_engine/astrocut_engine.py
- cutout/service/tasks.py
- cutout/service/cutout_engine/tests/test_des_engine.py
- cutout/service/cutout_engine/tests/test_astrocut_engine.py

Validacao executada:
- docker compose exec django isort --check-only cutout/service/cutout_engine/astrocut_engine.py cutout/service/cutout_engine/tests/test_astrocut_engine.py cutout/service/cutout_engine/tests/test_des_engine.py cutout/service/tasks.py cutout/service/cutout_engine/base.py cutout/service/cutout_engine/des_engine.py
- docker compose exec django black --check cutout/service/cutout_engine/astrocut_engine.py cutout/service/cutout_engine/tests/test_astrocut_engine.py cutout/service/cutout_engine/tests/test_des_engine.py cutout/service/tasks.py cutout/service/cutout_engine/base.py cutout/service/cutout_engine/des_engine.py
- docker compose exec django pytest cutout/service/cutout_engine/tests/test_des_engine.py cutout/service/cutout_engine/tests/test_astrocut_engine.py cutout/service/cutout_engine/tests/test_factory.py cutout/service/tests/test_tasks.py cutout/service/tests/test_cutout_parameters.py cutout/service/discovery/tests/test_des_csv_locator.py -q
- docker compose exec django python manage.py shell -c "... engine=legacy e engine=astrocut ..."
- Resultado: 17 passed; `engine=legacy` e `engine=astrocut` com status 200 e streaming FITS.

Status:
- Fase 3.1 concluida.
- Proxima etapa permanece focada em estabilizacao/expansao do engine astrocut sem alterar discovery DES.
