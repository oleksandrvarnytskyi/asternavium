# SPDX-License-Identifier: AGPL-3.0-or-later
from typing import Any

import pytest
from pydantic import ValidationError

from app.core.config import DEFAULT_AWS_REGION, Settings

_REQUIRED: dict[str, Any] = {
    "source_url": "https://example.org/asternavium",
    "app_table_name": "asternavium-test-table",
}


def _settings(**overrides: Any) -> Settings:
    return Settings(_env_file=None, **{**_REQUIRED, **overrides})


def test_settings_aws_region_defaults_to_frankfurt() -> None:
    assert _settings().aws_region == DEFAULT_AWS_REGION == "eu-central-1"


def test_settings_app_table_name_is_required() -> None:
    with pytest.raises(ValidationError, match="app_table_name"):
        Settings(_env_file=None, source_url=_REQUIRED["source_url"])


@pytest.mark.parametrize("name", ["ab", "bad name", "bad/name", "x" * 256])
def test_settings_app_table_name_rejects_invalid_dynamodb_name(name: str) -> None:
    with pytest.raises(ValidationError, match="app_table_name"):
        _settings(app_table_name=name)


@pytest.mark.parametrize("region", ["", "eu-central", "EU-CENTRAL-1", "eu_central_1"])
def test_settings_aws_region_rejects_malformed_region(region: str) -> None:
    with pytest.raises(ValidationError, match="aws_region"):
        _settings(aws_region=region)


@pytest.mark.parametrize("region", ["eu-central-1", "us-gov-west-1", "ap-southeast-2"])
def test_settings_aws_region_accepts_region_names(region: str) -> None:
    assert _settings(aws_region=region).aws_region == region
