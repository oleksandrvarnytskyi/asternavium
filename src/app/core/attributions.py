"""Credits for the third-party data the service uses, shown to API users."""

from dataclasses import dataclass
from typing import Final


@dataclass(frozen=True, slots=True)
class DataAttribution:
    """Credit for one third-party dataset.

    :ivar name: Name of the dataset or its publisher.
    :ivar url: Where the data comes from.
    :ivar license: SPDX identifier of the data licence.
    :ivar license_url: Full text of the data licence.
    """

    name: str
    url: str
    license: str
    license_url: str


DATA_ATTRIBUTIONS: Final[tuple[DataAttribution, ...]] = (
    DataAttribution(
        name="GeoNames",
        url="https://www.geonames.org/",
        license="CC-BY-4.0",
        license_url="https://creativecommons.org/licenses/by/4.0/",
    ),
)
