---
title: Implementação da Autenticação Federada SAML2 (djangosaml2)
description: Registro do plano executado para adicionar autenticação federada LIneA ao Cutout Service
date: 2026-07-18
branch: saml2_auth
status: implementado (pendências apenas de deploy)
references:
  - /home/glauber/linea/lsp_daiquiri
  - /home/glauber/linea/target
---

# Implementação da Autenticação Federada SAML2 (djangosaml2)

## Contexto

O Cutout Service passou a ter a mesma autenticação federada LIneA usada no `lsp_daiquiri` e no
`target`: proxy **SATOSA** (`satosa.linea.org.br`) na frente dos IdPs **CILogon** e **Rubin**
(`data.lsst.cloud`), com registro de usuários no **COmanage** (`register.linea.org.br`).

Como SAML **não pode ser testado localmente**, toda a solução fica atrás da variável de ambiente
`AUTH_SAML2_ENABLED` (default `False`, padrão vindo do lsp_daiquiri). Com a flag desligada, nada de
SAML é carregado e o login local continua pelo admin/allauth, sem nenhuma alteração de comportamento.

## Decisões de projeto

- **Toggle por env var** em `config/settings/base.py` (estilo lsp_daiquiri) combinado com a
  **parametrização** do target: `SITE_URL` (FQDN do SP), `SAML_SP_NAME` e diretórios em `config/`
  (`config/attribute-maps/`, `config/certificates/`).
- **Backend e views no app existente `cutout.users`** (equivalente ao módulo `common/` do target),
  evitando criar um app novo.
- **Campos `first_name`/`last_name` restaurados no model `User`** (o cookiecutter-django os havia
  removido). Com isso o `SAML_ATTRIBUTE_MAPPING` ficou idêntico aos repositórios de referência
  (`cn→first_name`, `sn→last_name`) e os nomes são persistidos no banco. O campo `name` foi mantido.
- **Correção de bug latente da referência**: `saml2_template_failure` usa
  `request.session.get("idp_name")` em vez de acesso direto — no original, um ACS que falhasse antes
  do backend rodar (ex.: erro de assinatura) causava `KeyError`/500 em vez da página de erro.

## O que foi feito

### Settings — `config/settings/base.py`

Bloco **incondicional** (existe com a flag on ou off):

- `AUTH_SAML2_ENABLED = env.bool("AUTH_SAML2_ENABLED", default=False)`
- `LINEA_LOGIN_URL` / `RUBIN_LOGIN_URL` (default `/admin/login/?next=/`) e
  `LINEA_REGISTER_URL` / `RUBIN_REGISTER_URL` (URLs de registro no COmanage), todos via env.
- `INTERNAL_GROUPS` — grupos do Django admin que o sync de grupos SAML nunca remove.
- `SETTINGS_EXPORT` + context processor `django_settings_export.settings_export` (todos os nomes
  exportados existem independente da flag; nomes ausentes quebrariam qualquer render).
- Handler e logger `djangosaml2` no `LOGGING` (`/data/log/djangosaml2.log`, rotativo 5 MB × 5).

Bloco **condicional** (`if AUTH_SAML2_ENABLED:`), porte do lsp_daiquiri com a parametrização do target:

- `INSTALLED_APPS += ["djangosaml2"]`, `AUTHENTICATION_BACKENDS += ["cutout.users.saml2.LineaSaml2Backend"]`,
  `MIDDLEWARE += ["djangosaml2.middleware.SamlSessionMiddleware"]`.
- `SAML_ACS_FAILURE_RESPONSE_FUNCTION = "cutout.users.views.saml2_template_failure"`,
  `SAML_SESSION_COOKIE_NAME`, `SESSION_COOKIE_SECURE=True`, `LOGIN_URL="/login/"`,
  `SAML_DEFAULT_BINDING=BINDING_HTTP_POST`, `SAML_CREATE_UNKNOWN_USER=True`, etc.
  (`LOGIN_REDIRECT_URL` permanece `"users:redirect"`.)
- `SAML_ATTRIBUTE_MAPPING`: `eduPersonUniqueId→username`, `cn→first_name`, `sn→last_name`,
  `email→email` (o username real vem do atributo `uid`, via backend).
- `SAML_CONFIG` completo: xmlsec em `/usr/bin/xmlsec1`, entityid `{SITE_URL}/saml2/metadata/`,
  endpoints ACS/SLO, respostas e requisições assinadas, os 4 metadados remotos do SATOSA
  (prod/dev × cilogon/rubin em `https://www.linea.org.br/static/metadata/`), certificados
  `config/certificates/mykey.pem`/`mycert.pem`, contato e organização LIneA.

### Backend — `cutout/users/saml2.py` (novo)

Porte do `LineaSaml2Backend` do lsp_daiquiri (idêntico ao do target):

- `authenticate()`: valida `session_info`/`ava`; grava `schacProjectMembership[0]` em
  `session["idp_name"]`; sem `uid` → `session["needs_registration"]=True` e retorna `None`;
  após autenticar, roda `setup_groups()` e bloqueia usuários com `schacUserStatus` ausente,
  `Pending` ou `PendingApproval`.
- `get_user_identifier()` lê o atributo `uid` e normaliza com `clean_user_main_attribute()`
  (troca `.` por `_`); `_extract_user_identifier_params()` busca o usuário por `username`.
- `setup_groups()`: sempre adiciona o grupo `saml2`, sincroniza os grupos do atributo `member` e
  remove os demais, preservando os listados em `INTERNAL_GROUPS`.

### Views — `cutout/users/views.py`

- `linea_login`: renderiza a página de escolha de IdP (`pages/linea_login.html`).
- `saml2_template_failure`: roteia os erros do ACS — precisa de registro (LIneA ou Rubin, conforme
  `idp_name == "rubin_oidc"`), aguardando aprovação, ou erro genérico — todos com status 403.

### URLs — `config/urls.py`

```python
if settings.AUTH_SAML2_ENABLED:
    urlpatterns += [
        path("saml2/", include("djangosaml2.urls")),
        path("login/", linea_login, name="login"),
    ]
```

Com a flag desligada, `/saml2/*` e `/login/` retornam 404 e o `allauth` (`accounts/`) segue intacto.

### Model — `cutout/users/models.py`

Removidas as linhas `first_name = None` / `last_name = None`; migration
`cutout/users/migrations/0002_user_first_name_user_last_name.py` criada e aplicada.

### Templates

- `cutout/templates/pages/linea_login.html`: seletor de IdP em Bootstrap 5 (estende o `base.html`
  do projeto) — botões "LSST Members (RSP account)" e "General Public", links de registro e helpdesk.
- `cutout/templates/djangosaml2/`: `linea_need_registration.html`, `rubin_need_registration.html`,
  `waiting_approval.html` e `login_error.html`, portados do lsp_daiquiri com um
  `base_error.html` compartilhado (mesmo visual standalone dos originais, sem CSS quadruplicado).
- Logo em `cutout/static/images/linea-logo.png`.

### Infraestrutura

- **Dockerfiles** (`compose/local/django/Dockerfile` e `compose/production/django/Dockerfile`):
  pacote `xmlsec1` adicionado (binário exigido pelo pysaml2).
- **`.envs/.local/.django`**: `AUTH_SAML2_ENABLED=False`.
- **`production.yml`**: volume `./config/certificates:/app/config/certificates:ro` no serviço django
  (propaga para celeryworker/beat/flower via âncora).
- **`config/certificates/README.md`**: receita openssl para certificado autoassinado
  (`mykey.pem`/`mycert.pem`).
- **`.gitignore`**: `config/certificates/*.pem|*.key|*.csr|*.crt` — chaves nunca são commitadas.
- **`requirements/base.txt`** (já estava): `djangosaml2>=1.12.0` e `django-settings-export==1.2.1`.
- **`README.md`**: seção "SAML2 Federated Authentication" com as variáveis de produção.

### Testes — `cutout/users/tests/test_saml2.py` (novo)

26 testes que rodam com a flag desligada (backend e views são import-safe):

- Unidades do backend: `clean_user_main_attribute`, `get_user_identifier` (7 variações),
  `is_authorized`, `user_can_authenticate`, early-exits do `authenticate` (inclusive a flag
  `needs_registration` na sessão) e `setup_groups` (sync, remoção e preservação de
  `INTERNAL_GROUPS`).
- `saml2_template_failure`: roteamento dos 4 templates + regressão da sessão vazia (fix do `.get()`).
- Wiring com flag off: nada de SAML nos settings, `/saml2/metadata/` e `/login/` → 404, login
  allauth intacto, context processor do settings-export renderizando a home.

## Verificação executada

Flag OFF (ambiente local):

- Suíte completa: **79 testes passando** (`pytest` no container, `config.settings.test`).
- Rotas: `/` → 200, `/accounts/login/` → 200, `/saml2/metadata/` → 404, `/login/` → 404.
- `flake8`/`mypy`/`black`/`isort` limpos nos arquivos alterados.

Flag ON (smoke, sem round-trip — SAML não é testável localmente):

- `manage.py check` com `AUTH_SAML2_ENABLED=True` + `SITE_URL` → sem erros.
- `djangosaml2.conf.get_config()` carregou o `SAML_CONFIG` completo: xmlsec1, certificados
  autoassinados de teste, attribute-maps e download real dos 4 metadados do SATOSA.
- Metadata XML do SP gerado com ACS e certificado (`saml2.metadata.entity_descriptor`).

## Pendências (deploy)

1. `just rebuild` local quando conveniente — o `xmlsec1` foi instalado ao vivo no container dev para
   o smoke test; o rebuild o traz da imagem.
2. Em produção: gerar certificados reais em `config/certificates/`, definir as env vars
   (`AUTH_SAML2_ENABLED=True`, `SITE_URL`, `SAML_SP_NAME`, `LINEA_LOGIN_URL`, `RUBIN_LOGIN_URL`,
   `LINEA_REGISTER_URL`, `RUBIN_REGISTER_URL`, `INTERNAL_GROUPS`).
3. Registrar o metadata do SP (`https://<SITE_URL>/saml2/metadata/`) junto à equipe SATOSA/LIneA —
   e reenviar sempre que o certificado mudar.
4. Validar em produção o fluxo completo: `/login/` → CILogon/Rubin, conta não registrada
   (página de registro) e conta pendente (aguardando aprovação).
