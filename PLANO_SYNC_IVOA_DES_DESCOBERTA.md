# Plano de Implementacao: Sync Cutout com Descoberta de Arquivos (IVOA)

Data: 2026-04-26
Escopo: endpoint sync primeiro, com modulo separado de descoberta de arquivos para DES
Publico: humanos + agentes de AI

Atualizacao de prioridade (2026-04-26):
- Este plano foi reordenado para refletir a execucao por prioridade de negocio (1 a 6).
- A semantica de erro em `text/plain` continua no plano geral SODA, mas foi explicitamente movida para depois da fase async.

## 1) Status de protocolos IVOA (atualizacao)

Baseado na pagina de standards do IVOA (https://www.ivoa.net/documents/):

- UWS: 1.1 (Recommendation, 2016-10-24)
- SODA: 1.0 (Recommendation, 2017-05-17)
- SIA: 2.0 (Recommendation, 2015-12-23)
- DataLink: 1.1 (Recommendation, 2023-12-15)
- DALI: 1.1 e 1.2 em progresso (PR no ciclo 2025)

Conclusao pratica para este projeto:
- Continuar modelando execucao assinc com UWS 1.1.
- Continuar modelando operacao de cutout com SODA 1.0.
- Para descoberta de arquivos por coordenada, usar padrao de descoberta SIA/ObsCore (ou TAP/ObsCore) + DataLink quando necessario.

## 2) Protocolo para "identificacao dos arquivos envolvidos"

Pergunta: existe um protocolo IVOA especifico para "dado coordenada, retornar lista de arquivos"?

Resposta curta:
- Nao ha um protocolo unico e isolado so para isso.
- O fluxo VO recomendado e:
  1. Descoberta de datasets por posicao com SIA 2.0 (ou TAP/ObsCore).
  2. Se um dataset tiver multiplos arquivos/derivacoes, usar DataLink para listar e qualificar links/arquivos/servicos.
  3. Depois chamar SODA para recorte (sync ou async).

Para este projeto (DES):
- Fase inicial: descoberta via catalogo local (CSV) e retorno de lista de arquivos internos.
- Evolucao: trocar o backend de descoberta para SIA/TAP/DataLink sem mudar contrato interno do sistema.

## 3) Objetivo tecnico imediato

Implementar o endpoint sync com pipeline claro:
1. Usuario envia coordenada + tamanho + parametros basicos.
2. Camada de policy valida se o usuario pode acessar o survey solicitado.
3. Modulo de descoberta identifica os arquivos DES envolvidos.
4. Modulo de cutout executa em task Celery (backend atual; depois astrocut).
5. Endpoint sync devolve resultado (arquivo ou redirect para resultado), mantendo semantica SODA-like.

Escopo funcional do endpoint sync nesta fase:
- aceitar os 3 tipos de pedido espacial: CIRCLE, RANGE e POLYGON
- para DES DR2 (publico), policy inicial retorna sempre true

## 4) Arquitetura alvo (modular)

## 4.1 Modulos novos (separados)

### A) modulo de descoberta de arquivos (novo)
Responsabilidade:
- Dado stencil (CIRCLE inicialmente) e survey/release, retornar lista de arquivos candidatos para cutout.

Contrato interno sugerido:

```python
class FileLocator(Protocol):
    def find_files(
        self,
        *,
        survey_id: str,
        stencil: dict,
        band: str | None = None,
    ) -> list[FileDescriptor]:
        ...
```

`FileDescriptor` minimo:
- dataset_id (opcional no inicio)
- file_path (ou URI)
- tile_id
- band
- metadados minimos de cobertura (opcional na v1)

Implementacao v1 (DES):
- `DesCsvFileLocator`
- Fonte: arquivo local com cobertura/tile/path

Implementacoes futuras:
- `SiaFileLocator` (consulta SIA 2.0)
- `TapObsCoreFileLocator` (consulta TAP/ObsCore)
- `DataLinkResolver` (expande dataset em links/arquivos)

### B) modulo de motor de cutout (abstracao)
Responsabilidade:
- Receber lista de arquivos + stencil + formato e produzir resultado.

Contrato interno sugerido:

```python
class CutoutEngine(Protocol):
    def run_cutout(
        self,
        *,
        files: list[FileDescriptor],
        stencil: dict,
        output_format: str,
        band: str | None,
        output_path: str,
    ) -> CutoutResult:
        ...
```

Implementacao v1:
- adapter sobre implementacao atual (DesCutout/base_cutout)

Implementacao v2:
- `AstrocutEngine` (troca transparente)

### C) orquestrador de job sync
Responsabilidade:
- Validar parametros
- Aplicar policy de acesso ao survey
- Chamar file locator
- Enfileirar task Celery
- Aguardar ate timeout sync
- Responder com arquivo ou redirect

### D) camada de policy de acesso por survey (novo)
Responsabilidade:
- Centralizar decisao de autorizacao para uso de survey/release no cutout.
- Permitir evolucao para surveys privados sem mudar endpoint e sem acoplamento com regra de negocio especifica.

Contrato interno sugerido:

```python
class SurveyAccessPolicy(Protocol):
  def can_request_cutout(
    self,
    *,
    user_id: str,
    survey_id: str,
    release: str | None = None,
  ) -> bool:
    ...
```

Implementacao v1 (agora):
- `DesPublicAccessPolicy`
- Comportamento: retorna sempre `True` para DES DR2 (dados publicos de teste)

Implementacoes futuras:
- `RoleBasedSurveyAccessPolicy`
- `ExternalAuthSurveyAccessPolicy` (LDAP/SSO/servico interno)

## 4.2 Fluxo Sync (alto nivel)

1. `GET/POST /api/sync`
2. Parse parametros (id/pos/format/band/runid)
3. Converter parametro espacial para stencil interno (CIRCLE, RANGE ou POLYGON)
4. `survey_access_policy.can_request_cutout(...)`
5. Se policy negar: retornar erro de autorizacao no formato padrao
6. `file_locator.find_files(...)`
7. Se vazio: retornar 204 (SODA sync sem pixels/sem match)
8. Enfileirar `run_sync_cutout_task.delay(...)`
9. Esperar resultado por janela limitada (ex: 20-30s)
10. Sucesso:
- opcao A: `FileResponse`
- opcao B: `303` para URL de resultado
11. Erro:
- resposta `text/plain` com prefixos SODA/DALI (UsageError, Error, ServiceUnavailable, MultiValuedParamNotSupported)

## 5) Contrato API Sync (proposta inicial)

## 5.1 Entrada (fase 1)
- `id` (ex: des_dr2)
- parametro espacial (3 formas suportadas no endpoint):
  - `pos=CIRCLE ra dec radius`
  - `pos=RANGE ra_min ra_max dec_min dec_max`
  - `pos=POLYGON ra1 dec1 ra2 dec2 ra3 dec3 ...`
- `format` (`fits` inicialmente; `png` opcional)
- `band` (custom DES, enquanto nao houver BAND padrao em metros)
- `runid` (opcional)

Observacao de compatibilidade VO:
- Em SODA 1.0, BAND padrao e intervalo em metros.
- Para DES no curto prazo, manter parametro custom de banda por letra, mas documentar como extensao local.

## 5.2 Saida
- 200 + stream de arquivo (ou 303 para URL de arquivo)
- 204 sem conteudo quando nao houver sobreposicao/arquivos
- 4xx/5xx em `text/plain` com prefixo de erro padronizado
- 403 para survey sem permissao (quando policy negar)

Exemplo de erro:
- `UsageError: invalid POS value`
- `MultiValuedParamNotSupported: only one POS in sync mode`
- `AuthorizationError: user has no access to requested survey`

## 6) Plano de execucao em fases

## Fase 0 - Hardening do prototipo atual
Objetivo:
- Limpar caminho minimo do sync para ficar previsivel.

Entregaveis:
- remover codigo morto/comentado do endpoint
- padronizar parse/validacao de parametros
- padronizar suporte de parse para CIRCLE/RANGE/POLYGON no endpoint
- padronizar respostas de erro text/plain

Criterios de aceite:
- endpoint sync com comportamento estavel para sucesso/falha
- testes de erro basicos passando

## Fase 1 - Modulo separado de descoberta (DES CSV)
Objetivo:
- introduzir separacao formal entre API e descoberta de arquivos

Entregaveis:
- pacote novo, ex: `cutout/service/discovery/`
- interface `FileLocator`
- implementacao `DesCsvFileLocator`
- testes unitarios para descoberta por CIRCLE/RANGE/POLYGON

Criterios de aceite:
- dado POS CIRCLE/RANGE/POLYGON conhecido, retorna lista coerente de arquivos
- endpoint sync usa o locator (sem chamar logica de tile diretamente)

## Fase 1.5 - Camada de policy de acesso
Objetivo:
- introduzir camada de autorizacao por survey, desacoplada da API e da descoberta.

Entregaveis:
- pacote novo, ex: `cutout/service/policies/`
- interface `SurveyAccessPolicy`
- implementacao inicial `DesPublicAccessPolicy` (retorna true)
- integracao da policy no fluxo do endpoint sync

Criterios de aceite:
- endpoint chama policy antes da descoberta/cutout
- para DES DR2, comportamento permanece liberado
- erro de autorizacao padronizado para surveys futuros privados

## Fase 2 - Orquestracao sync via Celery
Objetivo:
- executar pipeline completo no worker, mantendo semantica sync no endpoint

Entregaveis:
- task Celery `run_sync_cutout_task`
- payload de task contendo stencil + files + output spec
- retorno com caminho/URL do resultado

Criterios de aceite:
- endpoint sync gera resultado real
- tempos de timeout tratados com erro claro
- fase de job no banco ao menos em PENDING/QUEUED/COMPLETED/ERROR para sync

## Fase 3 - Adapter de motor de cutout
Objetivo:
- preparar troca para astrocut sem quebrar API

Entregaveis:
- interface `CutoutEngine`
- adapter engine atual
- stub/integracao inicial `AstrocutEngine`

Criterios de aceite:
- troca de engine por configuracao
- mesmos testes de endpoint continuam validos

## Fase 4 - Caminho VO de descoberta (futuro)
Objetivo:
- adicionar backend de descoberta por SIA/TAP/DataLink

Entregaveis:
- `SiaFileLocator` e/ou `TapObsCoreFileLocator`
- opcional `DataLinkResolver`

Criterios de aceite:
- mesmo endpoint sync funcionando com backend local ou remoto

## 7) Estrutura de codigo sugerida

```text
cutout/service/
  api/
    views.py
  policies/
    __init__.py
    base.py              # SurveyAccessPolicy
    des_public.py        # retorna True para DES DR2
  discovery/
    __init__.py
    base.py              # protocolos/interfaces
    des_csv_locator.py   # v1
    models.py            # FileDescriptor
  cutout_engine/
    __init__.py
    base.py              # CutoutEngine
    des_engine.py        # adapter atual
    astrocut_engine.py   # futuro
  orchestration/
    sync_service.py      # fluxo endpoint -> locator -> celery
  tasks.py               # tasks celery
```

## 8) Plano de testes (humanos + AI)

## 8.1 Unitarios
- parse POS (CIRCLE/RANGE/POLYGON validos e invalidos)
- DES CSV locator (match unico, multiplos tiles, vazio) para os 3 stencils
- policy de acesso (DES publico -> true)
- mapeamento de erros para prefixos SODA

## 8.2 Integracao
- endpoint sync -> celery -> resultado FITS
- caso sem overlap -> 204
- timeout do worker -> ServiceUnavailable
- endpoint sync com CIRCLE, RANGE e POLYGON
- fluxo com policy aplicada antes da descoberta

## 8.3 Contrato
- validacao de content-type de erro (`text/plain`)
- validacao de status codes esperados

## 9) Decisoes abertas (precisam de definicao)

1. No sync, retorno principal sera `200 file stream` ou `303 para URL`?
2. Limite de tempo do sync (timeout oficial)?
3. Parametro `band` custom DES sera mantido temporariamente com qual nome oficial?
4. Formatos suportados na fase 1: apenas FITS ou FITS+PNG?
5. Persistencia de resultados sync: por quanto tempo?

## 10) Backlog pronto para execucao por agentes AI

## Sprint A (infra de codigo)
- criar interfaces `SurveyAccessPolicy`, `FileLocator` e `CutoutEngine`
- criar `DesPublicAccessPolicy` (always true)
- criar `DesCsvFileLocator`
- adicionar testes unitarios de policy e locator

## Sprint B (sync funcional)
- criar `SyncCutoutService` (orquestracao)
- integrar endpoint `/api/sync` ao service
- garantir suporte no endpoint para CIRCLE/RANGE/POLYGON
- criar task celery unica para sync cutout
- implementar respostas de erro padrao

## Sprint C (qualidade)
- testes de integracao endpoint+celery
- metrica/log estruturado por runid/job
- documentacao OpenAPI atualizada

## Definition of Done (DoD)
- endpoint sync funcionando ponta a ponta com descoberta separada
- endpoint sync suportando CIRCLE, RANGE e POLYGON
- camada de policy integrada no fluxo (DES DR2 liberado)
- descoberta DES desacoplada da API
- task em worker separado via Celery
- testes cobrindo sucesso, vazio, erro e timeout
- documento de contrato API atualizado

## 11) Nota de compatibilidade com o estado atual do repositorio

Este plano assume refatoracao incremental sobre o prototipo existente, sem reescrever tudo de uma vez.
Prioridade imediata:
- estabilizar sync
- extrair descoberta de arquivos para modulo proprio
- manter possibilidade de troca do motor de recorte para astrocut.

## 12) Replanejamento priorizado (ordem de execucao)

## 12.1 Panorama do que ja esta pronto

- Discovery DES/CSV desacoplado com suporte de parse e descoberta para CIRCLE, RANGE e POLYGON.
- Policy de acesso por survey integrada antes do discovery.
- Pipeline sync com Celery e fases de job (PENDING/QUEUED/EXECUTING/COMPLETED/ERROR).
- Selecao de engine por parametro (`astrocut` default e `legacy` disponivel).
- Astrocut nativo atualmente operacional para `format=fits` com stencil `circle`.

## 12.2 Prioridade 1 - Suporte a PNG (inclui PNG colorido)

Objetivo:
- Adicionar `format=png` no pipeline sync, com suporte a PNG monocromatico e RGB.

Decisao de compatibilidade IVOA:
- Em SODA 1.0 nao existe parametro padrao para "PNG colorido"/composicao RGB.
- SODA define parametros como ID, POS/CIRCLE/POLYGON, BAND, TIME e POL; custom parameters sao permitidos.
- Portanto, o modo colorido sera extensao local documentada no contrato.

Contrato proposto:
- `format=png` ativa saida PNG.
- Novo parametro `color` (boolean):
  - `color=false` (default): PNG de banda unica.
  - `color=true`: PNG RGB composto.
- Novo parametro opcional `rgb_bands` (string): default `gri`.
  - Exemplo: `rgb_bands=gri` ou `rgb_bands=riz`.
- Regra de negocio:
  - Se `color=true` e `band` vier com banda unica, `rgb_bands` prevalece para composicao.
  - Se `color=false`, usa apenas `band`.

Implementacao esperada:
- Engine legacy: manter comportamento atual de referencia DES para PNG.
- Engine astrocut: implementar caminho de composicao RGB (3 bandas) e caminho monocromatico (1 banda).
- Task/policy: encaminhar `format`, `color` e bandas efetivas para o engine.

Criterios de aceite:
- `format=png&color=false&band=g` retorna PNG valido.
- `format=png&color=true&rgb_bands=gri` retorna PNG RGB valido.
- Validacoes claras para combinacoes invalidas de parametros.

## 12.3 Prioridade 2 - RANGE/POLYGON ponta a ponta

Objetivo:
- Garantir RANGE/POLYGON no fluxo completo da engine default, nao apenas no parse/discovery.

Escopo:
- Completar suporte do `astrocut` para RANGE e POLYGON.
- Se houver limitacao da biblioteca, implementar adaptacao geometrica controlada (ex: conversao para janela equivalente) sem quebrar contrato.

Criterios de aceite:
- Requests sync com `POS=RANGE ...` e `POS=POLYGON ...` executam com `engine=astrocut` e retornam resultado valido.
- Testes de integracao cobrindo CIRCLE/RANGE/POLYGON com engine default.

## 12.4 Prioridade 3 - Parametro para persistir resultado em data/results

Objetivo:
- Permitir controlar se o arquivo final sera persistido localmente em `data/results`.

Contrato proposto:
- Novo parametro `persist` (boolean):
  - `persist=false` (default): comportamento atual de resposta sync sem compromisso de retencao longa.
  - `persist=true`: manter arquivo final em `data/results`.

Regras:
- Definir naming deterministico por job/runid e evitar sobrescrita acidental.
- Registrar caminho final quando persistido.

Criterios de aceite:
- `persist=true` preserva arquivo em `data/results`.
- `persist=false` nao cria persistencia adicional alem do necessario para stream/resposta.

## 12.5 Prioridade 4 - Registro em banco para todos os pedidos sync

Objetivo:
- Registrar auditoria completa de cada pedido de cutout sync.

Campos minimos:
- usuario solicitante
- parametros usados
- status final (gerou resultado ou nao)
- tamanho do resultado em bytes
- tempo total de execucao

Observacao:
- Parte da estrutura ja existe via `Job`, `JobParameter`, `JobResult`, `start_time` e `end_time`, mas falta consolidar populacao obrigatoria para sync em todos os cenarios.

Criterios de aceite:
- Cada chamada sync gera registro auditavel com os campos minimos.
- Consultas administrativas conseguem listar historico por usuario e periodo.

## 12.6 Prioridade 5 - Atualizacao OpenAPI

Objetivo:
- Atualizar schema do endpoint sync com novos parametros e semantica atual.

Escopo minimo:
- Documentar `format=png`, `color`, `rgb_bands`, `persist`.
- Documentar suporte de POS (CIRCLE/RANGE/POLYGON) e limites conhecidos por engine.
- Documentar exemplos de request/response para FITS e PNG.

Criterios de aceite:
- OpenAPI e exemplos de uso alinhados com o comportamento real da API.

## 12.7 Prioridade 6 - Semantica de errors (postergada)

Decisao:
- Manter erros em JSON por enquanto.
- Migracao para semantica SODA/DALI (`text/plain` com prefixos padrao) fica para depois da fase async.

Criterios de aceite futuro:
- Contrato de erro unico para sync/async alinhado ao padrao IVOA.

## 13) Backlog operacional imediato (proxima sprint)

1. Implementar prioridade 1 (PNG mono + colorido) incluindo parametro `color` e `rgb_bands`.
2. Fechar prioridade 2 (RANGE/POLYGON ponta a ponta no engine default).
3. Incluir prioridade 3 (`persist`) e registro de caminho final.
4. Fechar prioridade 4 (auditoria completa sync em banco).
5. Atualizar prioridade 5 (OpenAPI e exemplos curl).
6. Manter prioridade 6 explicitamente adiada ate fase async.
