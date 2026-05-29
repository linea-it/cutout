# Plano de Implementacao - API Async UWS/SODA

Data de inicio: 2026-05-23
Escopo: implementar a superficie async do servico de cutout com UWS/SODA, usando workers em background, sem executar ainda o cutout cientifico real.
Publico: humanos e agentes de AI.

## Objetivo desta fase

Implementar a camada de API async para:

- receber os parametros corretos do pedido de cutout;
- criar jobs UWS no banco;
- enfileirar execucao em workers;
- expor endpoints para acompanhar job, parametros, fase e resultados;
- persistir resultados fake;
- manter a assinatura da funcao de worker compativel com a futura execucao real.

## Decisoes atuais

1. O endpoint sync existente permanece como esta.
2. A arvore async sera exposta em `/api/async`.
3. Nesta fase, o worker executa uma funcao fake, mas com assinatura compativel com o pipeline real.
4. O foco agora e fechar contrato de API, fila, transicoes de fase e retrieval de resultados.
5. A semantica final de erro SODA/DALI em `text/plain` continua adiada; vamos priorizar a estrutura UWS e o ciclo de vida dos jobs.

## Superficie de API planejada

### Colecao de jobs

- `POST /api/async`
  - cria um job async;
  - aceita parametros de cutout;
  - pode iniciar execucao imediatamente quando apropriado;
  - retorna `303 See Other` com `Location` apontando para o recurso do job.

- `GET /api/async`
  - lista jobs do usuario autenticado.

### Recurso de job

- `GET /api/async/{job_id}`
  - retorna metadados do job.

- `DELETE /api/async/{job_id}`
  - remove o job do usuario; se necessario, aborta antes.

### Fase do job

- `GET /api/async/{job_id}/phase`
  - retorna a fase atual do job.

- `POST /api/async/{job_id}/phase`
  - aceita ao menos `PHASE=RUN` e `PHASE=ABORT`.

### Parametros do job

- `GET /api/async/{job_id}/parameters`
  - retorna os parametros persistidos do job.

### Resultados do job

- `GET /api/async/{job_id}/results`
  - retorna a lista de resultados do job.

- `GET /api/async/{job_id}/results/{result_id}`
  - entrega ou redireciona para o artefato do resultado.

## Parametros da primeira iteracao

Nesta fase, a API async vai aceitar o mesmo conjunto de parametros hoje usado no fluxo sync atual:

- `id`
- `pos`
- `runid`
- `format`
- `band`
- `engine`
- `color`
- `rgb_bands`
- `persist`

## Regras de ciclo de vida

Fluxo esperado:

1. Criar job em `PENDING`.
2. Ao disparar execucao, registrar `message_id` e mover para `QUEUED`.
3. Worker ao iniciar move para `EXECUTING`.
4. Worker fake ao concluir persiste resultado(s) e move para `COMPLETED`.
5. Em falha, mover para `ERROR`.
6. Em cancelamento, mover para `ABORTED`.

## Worker fake

O worker fake deve manter a assinatura funcional esperada do processamento real:

`fake_image_cutout(job_id, source_id, stencil, engine, band, format, path, files=None, color=False, rgb_bands=None, persist=False)`

Ele pode gerar um arquivo pequeno em disco contendo um resumo dos parametros recebidos. Esse arquivo sera usado para validar:

- persistencia do resultado;
- endpoint de resultados;
- download do artefato.

## Evolucoes de modelo previstas

### Job

Manter o modelo atual e expandir o service para suportar:

- listagem por usuario;
- detalhe por usuario;
- start;
- abort;
- delete;
- registro de erro;
- registro de resultados.

### JobResult

Precisamos permitir retrieval real do resultado async. A direcao atual e adicionar campos para guardar o caminho e/ou URL do artefato persistido.

## Arquivos principais previstos

- `PLANO_ASYNC.md`
- `config/api_router.py`
- `cutout/service/api/views.py`
- `cutout/service/api/serializers.py`
- `cutout/service/uws/service.py`
- `cutout/service/uws/models.py`
- `cutout/service/policy.py`
- `cutout/service/tasks.py`
- `cutout/service/models/job_result.py`
- `cutout/service/migrations/*`
- testes em `cutout/service/tests/` ou pasta equivalente

## Sequencia de implementacao

### Fase 1 - scaffold da API async

- registrar rotas async;
- criar views para colecao, job, phase, parameters e results;
- centralizar parse de parametros.

### Fase 2 - service layer

- expandir `JobService` para ciclo completo do async;
- garantir ownership;
- implementar conversao de resultados persistidos.

### Fase 3 - fila e worker fake

- enfileirar execucao via Celery;
- registrar `message_id`;
- criar funcao fake e task de orquestracao do job;
- persistir `JobResult`.

### Fase 4 - resultados e download

- listar resultados;
- expor download por `result_id`.

### Fase 5 - testes e ajustes

- cobrir criacao, ownership, fases, resultados e download;
- atualizar este arquivo com decisoes relevantes conforme avancarmos.

## Status atual

- Scaffold principal da API async implementado.
- Endpoints async registrados em `config/api_router.py`.
- Job async criado e disparado automaticamente via worker fake.
- Persistencia de resultados fake implementada em `JobResult` com `url` e `file_path`.
- Download de resultado por `result_id` implementado.
- Testes da API async adicionados e passando.

## Criterios de aceite

1. `POST /api/async` cria job e retorna localizacao do recurso.
2. O job pode ser iniciado e passa por `QUEUED -> EXECUTING -> COMPLETED`.
3. `GET /api/async/{job_id}` reflete a fase correta.
4. `GET /parameters` retorna os parametros persistidos.
5. `GET /results` lista resultados fake persistidos.
6. `GET /results/{result_id}` entrega um artefato real.
7. Jobs de outros usuarios nao ficam acessiveis.

## Registro de decisoes

### 2026-05-23

- O arquivo de acompanhamento da fase async sera `PLANO_ASYNC.md`.
- A implementacao inicial prioriza a arvore de recursos UWS e o ciclo de vida dos jobs.
- A funcao cientifica principal continua fora de escopo nesta etapa.
- `POST /api/async` vai iniciar o job imediatamente por padrao, tratando ausencia de `PHASE` como `RUN`.
- Os detalhes de job, parametros e resultados serao retornados em JSON nesta primeira entrega, mantendo `GET/POST` de `phase` em formato textual.
- `JobResult` passa a persistir `url` e `file_path` para permitir listagem e download real do artefato fake.
- A task async fake recebe os mesmos argumentos estruturais do cutout real e grava um artefato simples em disco para exercitar retrieval.
- A serializacao enviada ao worker async usa apenas dados JSON-safe; objetos de stencil ficam restritos ao fluxo sync.
- O lint foi explicitamente postergado nesta etapa para priorizar o fluxo funcional da API async.

## Validacoes executadas

- `pytest cutout/service/tests/test_async_api.py -q` -> 4 passed

## Arquivos alterados nesta etapa

- `PLANO_ASYNC.md`
- `config/api_router.py`
- `cutout/service/api/views.py`
- `cutout/service/api/serializers.py`
- `cutout/service/models/job_result.py`
- `cutout/service/migrations/0003_jobresult_storage_fields.py`
- `cutout/service/policy.py`
- `cutout/service/tasks.py`
- `cutout/service/tests/test_async_api.py`
- `cutout/service/uws/models.py`
- `cutout/service/uws/service.py`
