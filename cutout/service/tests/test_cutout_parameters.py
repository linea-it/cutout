from cutout.service.cutout_parameters import CutoutParameters
from cutout.service.uws.models import JobParameter


def test_cutout_parameters_parses_engine() -> None:
    params = [
        JobParameter(parameter_id="id", value="des_dr2"),
        JobParameter(parameter_id="pos", value="CIRCLE 10 0 1"),
        JobParameter(parameter_id="band", value="g"),
        JobParameter(parameter_id="format", value="fits"),
        JobParameter(parameter_id="engine", value="legacy"),
    ]

    parsed = CutoutParameters.from_job_parameters(params)

    assert parsed.engines == ["legacy"]
    assert parsed.ids == ["des_dr2"]


def test_cutout_parameters_without_engine_keeps_empty_list() -> None:
    params = [
        JobParameter(parameter_id="id", value="des_dr2"),
        JobParameter(parameter_id="pos", value="CIRCLE 10 0 1"),
        JobParameter(parameter_id="band", value="g"),
        JobParameter(parameter_id="format", value="fits"),
    ]

    parsed = CutoutParameters.from_job_parameters(params)

    assert parsed.engines == []
