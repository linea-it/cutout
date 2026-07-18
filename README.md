# cutout

LIneA Cutout Service

[![Built with Cookiecutter Django](https://img.shields.io/badge/built%20with-Cookiecutter%20Django-ff69b4.svg?logo=cookiecutter)](https://github.com/cookiecutter/cookiecutter-django/)
[![Black code style](https://img.shields.io/badge/code%20style-black-000000.svg)](https://github.com/ambv/black)

License: MIT

[Requisitos](exemplo_adriano/docs/definicao_requisitos/Requisitos.md)

Tiles do DES para teste: [Sample Tiles](https://scienceserver.linea.org.br/data/cutout_des_sample_tiles.tar.gz)

## Settings

Moved to [settings](http://cookiecutter-django.readthedocs.io/en/latest/settings.html).

## Development URLs

- Home: <http://localhost:8000>
- Admin: <http://localhost:8000/admin/>
- API REST: <http://localhost:8000/api/>
- MailHog (emails enviados pela aplicação): <http://127.0.0.1:8025/>
- Celery Flower: <http://localhost:5555>
- Project Docs : <http://localhost:9000>

## Basic Commands

### Setting Up Your Users

- To create a **normal user account**, just go to Sign Up and fill out the form. Once you submit it, you'll see a "Verify Your E-mail Address" page. Go to your console to see a simulated email verification message. Copy the link into your browser. Now the user's email should be verified and ready to go.

- To create a **superuser account**, use this command:

      python manage.py createsuperuser

For convenience, you can keep your normal user logged in on Chrome and your superuser logged in on Firefox (or similar), so that you can see how the site behaves for both kinds of users.

### Pre commit

Running pre-commit checks:

    ```bash
    pre-commit
    ```

### Type checks

Running type checks with mypy:

    mypy cutout

### Test coverage

To run the tests, check your test coverage, and generate an HTML coverage report:

    coverage run -m pytest
    coverage html
    open htmlcov/index.html

#### Running tests with pytest

    pytest

### Live reloading and Sass CSS compilation

Moved to [Live reloading and SASS compilation](https://cookiecutter-django.readthedocs.io/en/latest/developing-locally.html#sass-compilation-live-reloading).

### Celery

This app comes with Celery.

To run a celery worker:

```bash
cd cutout
celery -A config.celery_app worker -l info
```

Please note: For Celery's import magic to work, it is important _where_ the celery commands are run. If you are in the same folder with _manage.py_, you should be right.

To run [periodic tasks](https://docs.celeryq.dev/en/stable/userguide/periodic-tasks.html), you'll need to start the celery beat scheduler service. You can start it as a standalone process:

```bash
cd cutout
celery -A config.celery_app beat
```

or you can embed the beat service inside a worker with the `-B` option (not recommended for production use):

```bash
cd cutout
celery -A config.celery_app worker -B -l info
```

### Email Server

In development, it is often nice to be able to see emails that are being sent from your application. For that reason local SMTP server [MailHog](https://github.com/mailhog/MailHog) with a web interface is available as docker container.

Container mailhog will start automatically when you will run all docker containers.
Please check [cookiecutter-django Docker documentation](http://cookiecutter-django.readthedocs.io/en/latest/deployment-with-docker.html) for more details how to start all containers.

With MailHog running, to view messages that are sent by your application, open your browser and go to `http://127.0.0.1:8025`

### Sentry

Sentry is an error logging aggregator service. You can sign up for a free account at <https://sentry.io/signup/?code=cookiecutter> or download and host it yourself.
The system is set up with reasonable defaults, including 404 logging and integration with the WSGI application.

You must set the DSN url in production.

## Deployment

The following details how to deploy this application.

### Docker

See detailed [cookiecutter-django Docker documentation](http://cookiecutter-django.readthedocs.io/en/latest/deployment-with-docker.html).

### SAML2 Federated Authentication (djangosaml2)

Autenticação federada LIneA (proxy SATOSA → CILogon e Rubin), mesma solução usada no `lsp_daiquiri` e no `target`.

SAML **não pode ser testado localmente**. O comportamento é controlado pela variável `AUTH_SAML2_ENABLED`
(default `False`): desligada, nada de SAML é carregado e o login é pelo admin/allauth; ligada, o backend
`cutout.users.saml2.LineaSaml2Backend` é adicionado, as rotas `saml2/` e `/login/` (seletor de IdP) são
montadas e `LOGIN_URL` passa a ser `/login/`.

Variáveis de ambiente para produção (`.envs/.production/.django`):

- `AUTH_SAML2_ENABLED=True`
- `SITE_URL=https://cutout.linea.org.br` (FQDN do SP, sem barra final)
- `SAML_SP_NAME` (default `SP Cutout Service`)
- `LINEA_LOGIN_URL` — ex.: `https://<host>/saml2/login/?idp=https://satosa.linea.org.br/linea/proxy/aHR0cHM6Ly9jaWxvZ29uLm9yZw==`
- `RUBIN_LOGIN_URL` — variante para o frontend Rubin do SATOSA
- `LINEA_REGISTER_URL` / `RUBIN_REGISTER_URL` — URLs de registro no COmanage
- `INTERNAL_GROUPS` — lista (separada por vírgula) de grupos do Django admin que o sync SAML nunca remove

Requisitos adicionais com a flag ligada:

- Certificados do SP em `config/certificates/` (`mykey.pem`/`mycert.pem`) — ver `config/certificates/README.md`;
  em produção o diretório é montado como volume (`production.yml`). Ligar a flag exige HTTPS
  (`SESSION_COOKIE_SECURE=True`).
- O metadata do SP (`https://<SITE_URL>/saml2/metadata/`) deve ser registrado junto à equipe SATOSA/LIneA
  (reenviar sempre que o certificado mudar).
- O binário `xmlsec1` já é instalado nas imagens Docker (requisito do pysaml2).
