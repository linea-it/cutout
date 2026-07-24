"""Bateria manual de testes do `perform_cutout` baseada em exemplos.txt.

Cenários já validados no fluxo sync, usando os FITS reais Y6A1/r4907 em
/data/tiles/des_dr2 (disponíveis no container).

Uso (dentro do container):

    docker compose exec django python manage.py shell

    >>> from cutout.service.teste_cutout_runner import run_exemplo, run_todos
    >>> run_exemplo(1)          # cria Job+Task e executa perform_cutout direto
    >>> run_todos()             # cenários 1 a 8
    >>> job, task = run_exemplo(9, dispatch=False)   # só cria; executar via worker:
    >>> from cutout.service.tasks import perform_cutout_task
    >>> perform_cutout_task.delay(job.id, task.id)
"""

from __future__ import annotations

from pathlib import Path

from cutout.service.cutout_runner import perform_cutout
from cutout.service.uws.models import JobParameter
from cutout.service.uws.service import JobService

EXEMPLOS = {
    1: {
        "params": {"pos": "CIRCLE 0.5 0.017 0.016667", "band": "g", "format": "fits"},
        "esperado": "COMPLETED — FITS ~0.8MB, 1 tile (DES0002+0001, 1')",
    },
    2: {
        "params": {"pos": "CIRCLE 1.25 -0.683 0.05", "band": "z", "format": "fits"},
        "esperado": "COMPLETED — FITS ~7.2MB (DES0005-0041, 3')",
    },
    3: {
        "params": {"pos": "CIRCLE 0.75 2.867 0.033333", "format": "png", "color": "true", "rgb_bands": "gri"},
        "esperado": "COMPLETED — PNG RGB ~2.0MB (DES0003+0252, 2')",
    },
    4: {
        "params": {"pos": "CIRCLE 0.5 0.017 0.116667", "band": "Y", "format": "fits"},
        "esperado": "COMPLETED — FITS ~38.9MB (DES0002+0001, 7')",
    },
    5: {
        "params": {"pos": "CIRCLE 1.10 2.50 0.083333", "band": "r", "format": "fits"},
        "esperado": "COMPLETED — mosaico de 2 tiles, header com NINPUTS=2 (5')",
    },
    6: {
        "params": {"pos": "CIRCLE 1.07 2.15 0.083333", "band": "r", "format": "fits"},
        "esperado": "COMPLETED — cobertura parcial, borda leste preenchida com zeros (5')",
    },
    7: {
        "params": {"pos": "CIRCLE 10.0 10.0 0.016667", "band": "r", "format": "fits"},
        "esperado": "Task ERROR — 'No available files on disk...' (fora do footprint)",
    },
    8: {
        "params": {"pos": "CIRCLE 0.5 1.0 0.166667", "band": "r", "format": "fits"},
        "esperado": "Task ERROR — vão entre tiles (Dec entre DES0002+0001 e DES0002+0209)",
    },
    9: {
        "params": {"pos": "CIRCLE 0.5 2.15 0.25", "band": "i", "format": "fits"},
        "esperado": "COMPLETED via worker — 15', caso que estoura o timeout do sync",
    },
}


def _get_user(username: str | None = None):
    from cutout.users.models import User

    if username:
        return User.objects.get(username=username)
    return User.objects.filter(username="dev").first() or User.objects.first()


def create_job_exemplo(n: int, user=None):
    """Cria Job + Tasks (sem despachar) para o cenário `n` e retorna (job, task)."""
    scenario = EXEMPLOS[n]
    params = [JobParameter(parameter_id="id", value="des_dr2", is_post=True)]
    params += [JobParameter(parameter_id=key, value=value, is_post=True) for key, value in scenario["params"].items()]

    job = JobService().create(user=user or _get_user(), params=params, run_id=f"teste_exemplo_{n}")
    task = job.tasks.order_by("sequence").first()
    return job, task


def _print_status(job, task) -> None:
    job.refresh_from_db()
    task.refresh_from_db()

    print(f"  Job {job.id}: phase={job.phase} start={job.start_time} end={job.end_time}")
    print(f"  Task {task.id}: status={task.status} start={task.start_time} end={task.end_time}")
    if task.error_message:
        print(f"  Task error_message: {task.error_message}")

    for result in job.results.order_by("sequence"):
        exists = Path(result.file_path).exists() if result.file_path else False
        print(
            f"  Result {result.result_id}: size={result.size} mime={result.mime_type} "
            f"path={result.file_path} exists={exists}"
        )
    if not job.results.exists():
        print("  Sem JobResult registrado.")


def run_exemplo(n: int, user=None, dispatch: bool = True):
    """Executa o cenário `n` chamando perform_cutout(job_id, task_id) diretamente.

    Com dispatch=False apenas cria o Job+Task (para despachar manualmente via
    perform_cutout_task.delay e observar o worker).
    """
    scenario = EXEMPLOS[n]
    print(f"=== Exemplo {n}: {scenario['params']}")
    print(f"    Esperado: {scenario['esperado']}")

    job, task = create_job_exemplo(n, user)
    print(f"    Criado job_id={job.id} task_id={task.id}")

    if not dispatch:
        print("    Despache com: perform_cutout_task.delay(job.id, task.id)")
        return job, task

    try:
        result = perform_cutout(job.id, task.id)
        print(f"    perform_cutout retornou: {result}")
    except Exception as exc:
        print(f"    perform_cutout levantou: {type(exc).__name__}: {exc}")

    _print_status(job, task)
    return job, task


def run_todos(user=None) -> None:
    """Roda os cenários 1 a 8 (o 9 é grande — rodar via worker com dispatch=False)."""
    for n in range(1, 9):
        run_exemplo(n, user=user)
        print()
