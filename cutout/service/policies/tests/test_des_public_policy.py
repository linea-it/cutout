from cutout.service.policies import DesPublicAccessPolicy


def test_des_public_policy_allows_des_dr2() -> None:
    policy = DesPublicAccessPolicy()

    allowed = policy.can_request_cutout(user_id="123", survey_id="des_dr2")

    assert allowed is True


def test_des_public_policy_denies_unknown_survey() -> None:
    policy = DesPublicAccessPolicy()

    allowed = policy.can_request_cutout(user_id="123", survey_id="private_survey")

    assert allowed is False
