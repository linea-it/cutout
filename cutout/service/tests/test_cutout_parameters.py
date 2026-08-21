from cutout.service.cutout_parameters import CutoutParameters
from cutout.service.exceptions import InvalidCutoutParameterError
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


def test_cutout_parameters_without_engine_defaults_to_astrocut() -> None:
    params = [
        JobParameter(parameter_id="id", value="des_dr2"),
        JobParameter(parameter_id="pos", value="CIRCLE 10 0 1"),
        JobParameter(parameter_id="band", value="g"),
        JobParameter(parameter_id="format", value="fits"),
    ]

    parsed = CutoutParameters.from_job_parameters(params)

    assert parsed.engines == ["astrocut"]


def test_cutout_parameters_rejects_path_traversal_band() -> None:
    params = [
        JobParameter(parameter_id="id", value="des_dr2"),
        JobParameter(parameter_id="pos", value="CIRCLE 10 0 1"),
        JobParameter(parameter_id="band", value="x/../../../lsst_dp1/SECRET/secret"),
        JobParameter(parameter_id="format", value="fits"),
    ]

    try:
        CutoutParameters.from_job_parameters(params)
    except InvalidCutoutParameterError as exc:
        assert "Unsafe band" in str(exc)
    else:
        raise AssertionError("Expected InvalidCutoutParameterError for traversal band")


def test_cutout_parameters_allows_future_survey_band_token() -> None:
    params = [
        JobParameter(parameter_id="id", value="des_dr2"),
        JobParameter(parameter_id="pos", value="CIRCLE 10 0 1"),
        JobParameter(parameter_id="band", value="u"),
        JobParameter(parameter_id="format", value="fits"),
    ]

    parsed = CutoutParameters.from_job_parameters(params)

    assert parsed.bands == ["u"]


def test_cutout_parameters_rejects_invalid_rgb_bands() -> None:
    params = [
        JobParameter(parameter_id="id", value="des_dr2"),
        JobParameter(parameter_id="pos", value="CIRCLE 10 0 1"),
        JobParameter(parameter_id="band", value="g"),
        JobParameter(parameter_id="rgb_bands", value="g/../r"),
        JobParameter(parameter_id="format", value="png"),
    ]

    try:
        CutoutParameters.from_job_parameters(params)
    except InvalidCutoutParameterError as exc:
        assert "Unsafe band" in str(exc)
    else:
        raise AssertionError("Expected InvalidCutoutParameterError for invalid rgb_bands")
