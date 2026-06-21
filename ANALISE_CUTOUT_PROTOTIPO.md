# Analise do prototipo do app Django cutout

Data da analise: 2026-04-26

## Objetivo desta analise
Avaliar o que foi realmente implementado no prototipo, com foco em:
- API e endpoints
- parametros de entrada (estilo VO/SODA/UWS)
- identificacao de arquivos FITS envolvidos no cutout por coordenada
- worker separado, fila e distribuicao de tarefas

Tambem foi feita uma comparacao com referencias VO encontradas no codigo.

## Referencias VO encontradas no repositorio

### UWS (link explicito no codigo)
- cutout/service/uws/models.py
  - https://www.ivoa.net/documents/UWS/20161024/REC-UWS-1.1-20161024.html
- cutout/service/models/job.py
- cutout/service/models/job_parameter.py
- cutout/service/models/job_result.py
  - todos mencionam implementacao baseada no UWS 1.1

### SODA/VO (mencoes no codigo e anotacoes)
- cutout/service/api/views.py
  - comentario sobre IVOA/SODA/WD-SODA 3.2.2 para parametro BAND
  - comentario com referencia ao projeto lsst-sqre/vo-cutouts
- Anotacoes.md
  - item sobre SODA BAND
  - item sobre DALI 3.2.1 (-Inf/+Inf em intervalos)
  - item sobre formato de erro esperado pelo SODA

### Verificacao externa (VO)
Foi consultado o conteudo de:
- UWS 1.1 (IVOA)
- SODA 1.0 (IVOA)

Resumo normativo relevante para este projeto:
- SODA: recursos sync e async, parametros como ID, POS/CIRCLE/POLYGON, BAND, TIME, POL, erros em text/plain com prefixos padrao (UsageError, MultiValuedParamNotSupported, etc).
- UWS: arvore de recursos de job (lista, job, phase, parameters, results, destruction, executionduration, abort/start), fases padronizadas e operacoes REST para controle de job.

## O que esta implementado de fato

### 1) Endpoints expostos hoje
Arquivos:
- config/urls.py
- config/api_router.py
- cutout/service/api/views.py

Implementado:
- GET /api/cutout
  - retorna mensagem fixa "Hello, world!"
- GET /api/sync
  - aceita query params
  - converte params para JobParameter
  - cria job e chama inicio do processamento via JobService
  - resposta atual: JSON {"success": true}

Importante:
- Nao ha endpoint async estilo UWS exposto ao cliente (ex.: /jobs, /jobs/{id}, /jobs/{id}/phase, /jobs/{id}/results).
- JobRequestViewSet existe no codigo, mas nao esta registrado no router.
- SyncCutoutView tem muito codigo comentado de uma versao anterior (retorno de FITS/PNG por FileResponse), sem estar ativo na versao atual.

### 2) Modelo de parametros (parcialmente VO-like)
Arquivos:
- cutout/service/api/views.py
- cutout/service/cutout_parameters.py
- cutout/service/stencils.py

Implementado:
- Parametros aceitos/documentados no schema do endpoint sync:
  - id
  - pos (CIRCLE/RANGE/POLYGON dentro da string)
  - runid
  - format
  - band
- Parser de stencil:
  - POS com CIRCLE, RANGE, POLYGON
  - CIRCLE e POLYGON diretos tambem sao aceitos no parser (pela logica parse_stencil)
- Validacao de negocio no policy:
  - apenas 1 id
  - apenas 1 stencil
  - RANGE rejeitado no momento

Lacunas importantes:
- Nao ha implementacao completa dos parametros SODA padrao (TIME, POL, etc).
- BAND foi modelado como string de banda (g,r,i,z,Y), nao como intervalo em metros (como no SODA 1.0).
- Multiplicidade de parametros existe no parser/listas, mas fluxo funcional esta restrito a um unico id e um unico stencil.

### 3) Fila, worker separado e escalabilidade
Arquivos:
- config/celery_app.py
- config/settings/base.py
- docker-compose.yml
- production.yml
- cutout/service/tasks.py
- cutout/service/policy.py
- cutout/service/uws/service.py

Implementado:
- Infra de fila baseada em Celery + Redis esta configurada.
- Servicos separados em compose para:
  - django
  - redis
  - celeryworker
  - celerybeat
  - flower
- JobService chama policy.dispatch, que envia tarefas para Celery.

Pontos ainda incompletos/inconsistentes:
- dispatch atual usa chord(headers[0])(callback), ou seja, efetivamente nao executa grupo completo de tarefas; so usa o primeiro header.
- callback job_completed nao atualiza corretamente estado UWS no banco (funcao retorna string de teste).
- task image_cutout retorna string fixa "Resultado do cutout 1", sem metadados de resultado UWS persistidos.
- transicoes de fase estao incompletas (QUEUED parcial; EXECUTING/COMPLETED/ERROR sem fluxo robusto de ponta a ponta).

### 4) Identificacao dos arquivos FITS por coordenada
Arquivos:
- cutout/lib/des_cutout.py
- cutout/lib/base_cutout.py
- cutout/lib/cutout.py

Implementado (parte cientifica do recorte para DES):
- calculo de vertices do cutout a partir de RA/DEC/size
- leitura de catalogo de tiles (dr2_tiles.csv)
- identificacao dos tiles que cobrem os vertices
- derivacao de paths de arquivos FITS comprimidos (.fits.fz)
- descompressao on-demand com funpack para /data/tmp
- leitura parcial via astropy Cutout2D e montagem quando cruza 1, 2 ou 3 tiles
- geracao de saida FITS
- geracao de PNG Lupton (gri)

Lacunas:
- logica de identificacao de tile usa matching simples por bounding box e assume que sempre encontra indice valido (risco de excecao em bordas/falhas).
- nao ha camada de abstracao para varios surveys pronta em producao (apenas des_dr2 implementado).
- RANGE/POLYGON nao estao implementados de ponta a ponta no backend de execucao atual.

### 5) Persistencia de jobs e resultados
Arquivos:
- cutout/service/models/job.py
- cutout/service/models/job_parameter.py
- cutout/service/models/job_result.py
- cutout/service/uws/models.py
- cutout/service/uws/job.py

Implementado:
- tabelas para Job, JobParameter, JobResult
- fases UWS no modelo de Job
- run_id, owner, creation/start/end/destruction/execution_duration/quote

Lacunas:
- escrita efetiva de JobResult durante processamento nao esta fechada
- erro UWS (errorSummary/detail) nao esta modelado e persistido de forma completa
- endpoints de consulta/gestao de jobs nao estao expostos

## Comparacao objetiva com o esperado (VO + requisitos do projeto)

### Requisito: API VO-compliant para cutout
Status: PARCIAL
- Existe tentativa de alinhar com UWS/SODA em nomenclatura e parser de POS.
- Falta contrato completo de API SODA/UWS (principalmente endpoints async UWS e respostas/payloads padronizados).

### Requisito: receber coordenada/tamanho ou lista
Status: PARCIAL
- Coordenada unica com POS=CIRCLE entra no fluxo.
- Lista/multiplos valores nao esta pronta no fluxo final (restrito por policy).

### Requisito: identificar arquivos pela coordenada e gerar resultado
Status: PARCIALMENTE IMPLEMENTADO
- Identificacao de tiles/arquivos DES e recorte FITS existe no backend cientifico.
- Integracao robusta com retorno de resultado via API/UWS ainda incompleta.

### Requisito: worker separado e escalavel
Status: BASE IMPLEMENTADA, FLUXO INCOMPLETO
- Infra de worker separado e fila existe (Celery + Redis + containers dedicados).
- Orquestracao completa do ciclo de vida dos jobs e resultados ainda incompleta.

### Requisito: sistema de fila e distribuicao de tasks
Status: PARCIAL
- Fila existe.
- Distribuicao atual de tarefas em chord/group nao esta finalizada para multiplos itens.

## Principais gaps para concluir o servico

1. Expor API UWS/SODA completa (sync + async) com recursos de job padronizados.
2. Implementar respostas de erro no formato SODA (text/plain com prefixos corretos).
3. Finalizar ciclo de vida do job: PENDING -> QUEUED -> EXECUTING -> COMPLETED/ERROR/ABORTED.
4. Persistir resultados reais (JobResult com URL, mime_type, size) e disponibilizar download.
5. Implementar de fato multiplos inputs (lista de coordenadas e combinacoes de parametros) de forma escalavel.
6. Revisar parametro BAND para compatibilidade com SODA (ou declarar extensao custom com metadados claros).
7. Implementar endpoints/fluxos de monitoramento e gestao de jobs do usuario.
8. Fechar politicas de retencao/garbage collector para resultados e temporarios.

## Conclusao executiva
O projeto ja tem uma base tecnica relevante: parser de stencils, modelos de job inspirados em UWS, infraestrutura Celery/Redis com worker separado e implementacao cientifica de cutout DES com identificacao de tiles por coordenada.

Porem, no estado atual ele ainda e um prototipo incompleto no que mais importa para operacao VO-compliant: contrato de API UWS/SODA de ponta a ponta, fluxo async padronizado, ciclo de vida completo de jobs e publicacao de resultados/erros no formato esperado.

Em resumo: o nucleo de processamento existe, a infraestrutura de fila existe, mas a camada de produto/API padrao VO ainda nao esta finalizada.