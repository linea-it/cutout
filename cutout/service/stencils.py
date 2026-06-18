"""Parsing and representation of stencil parameters."""
from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Any

from astropy import units as u
from astropy.coordinates import Angle, SkyCoord

Range = tuple[float, float]


class Stencil(ABC):
    """Base class for a stencil parameter."""

    @classmethod
    @abstractmethod
    def from_string(cls, params: str) -> Stencil:
        """Parse a string representation of stencil parameters to an object."""

    @abstractmethod
    def to_dict(self) -> dict[str, Any]:
        """Convert the stencil to a JSON-serializable form for queuing."""

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> Stencil:
        """Reconstruct a stencil from its ``to_dict`` representation."""
        stencil_type = data.get("type", "circle")
        if stencil_type == "circle":
            return CircleStencil(
                center=SkyCoord(data["center"]["ra"] * u.deg, data["center"]["dec"] * u.deg, frame="icrs"),
                radius=Angle(data["radius"] * u.deg),
            )
        elif stencil_type == "polygon":
            ras = [v[0] for v in data["vertices"]]
            decs = [v[1] for v in data["vertices"]]
            return PolygonStencil(vertices=SkyCoord(ras * u.degree, decs * u.degree, frame="icrs"))
        elif stencil_type == "range":
            return RangeStencil(ra=data["ra"], dec=data["dec"])
        else:
            raise ValueError(f"Unknown stencil type: {stencil_type}")

    @abstractmethod
    def get_center(self) -> SkyCoord:
        """Return the central coordinate for the cutout."""

    @abstractmethod
    def get_cutout_size(self):
        """Return the cutout size with units preserved."""


@dataclass
class CircleStencil(Stencil):
    """Represents a ``CIRCLE`` or ``POS=CIRCLE`` stencil."""

    center: SkyCoord
    radius: Angle

    @classmethod
    def from_string(cls, params: str) -> CircleStencil:
        ra, dec, radius = (float(p) for p in params.split())
        return cls(
            center=SkyCoord(ra * u.degree, dec * u.degree, frame="icrs"),
            radius=Angle(radius * u.degree),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "type": "circle",
            "center": {
                "ra": self.center.ra.degree,
                "dec": self.center.dec.degree,
            },
            "radius": self.radius.degree,
        }

    def get_center(self) -> SkyCoord:
        return self.center

    def get_cutout_size(self):
        return 2 * self.radius


@dataclass
class PolygonStencil(Stencil):
    """Represents a ``POLYGON`` or ``POS=POLYGON`` stencil.

    Represents the polygon defined by the given vertices.  Polygon winding
    must be counter-clockwise when viewed from the origin towards the sky.
    """

    vertices: SkyCoord

    @classmethod
    def from_string(cls, params: str) -> PolygonStencil:
        data = [float(p) for p in params.split()]
        if len(data) % 2 != 0:
            msg = f"Odd number of coordinates in vertex list {params}"
            raise ValueError(msg)
        if len(data) < 6:
            msg = "Polygons require at least three vertices"
            raise ValueError(msg)
        ras = []
        decs = []
        for i in range(0, len(data), 2):
            ras.append(data[i])
            decs.append(data[i + 1])
        vertices = SkyCoord(ras * u.degree, decs * u.degree, frame="icrs")
        return cls(vertices=vertices)

    def to_dict(self) -> dict[str, Any]:
        return {
            "type": "polygon",
            "vertices": [(v.ra.degree, v.dec.degree) for v in self.vertices],
        }

    def get_center(self) -> SkyCoord:
        ras = self.vertices.ra.degree
        decs = self.vertices.dec.degree
        return SkyCoord(
            ra=(ras.min() + ras.max()) / 2 * u.deg,
            dec=(decs.min() + decs.max()) / 2 * u.deg,
            frame="icrs",
        )

    def get_cutout_size(self):
        ras = self.vertices.ra.degree
        decs = self.vertices.dec.degree
        return [(ras.max() - ras.min()) * u.deg, (decs.max() - decs.min()) * u.deg]


@dataclass
class RangeStencil(Stencil):
    """Represents a ``POS=RANGE`` stencil."""

    ra: Range
    dec: Range

    @classmethod
    def from_string(cls, params: str) -> RangeStencil:
        ra_min, ra_max, dec_min, dec_max = (float(p) for p in params.split())
        return cls(
            ra=(ra_min, ra_max),
            dec=(dec_min, dec_max),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "type": "range",
            "ra": self.ra,
            "dec": self.dec,
        }

    def get_center(self) -> SkyCoord:
        return SkyCoord(
            ra=(self.ra[0] + self.ra[1]) / 2 * u.deg,
            dec=(self.dec[0] + self.dec[1]) / 2 * u.deg,
            frame="icrs",
        )

    def get_cutout_size(self):
        return [(self.ra[1] - self.ra[0]) * u.deg, (self.dec[1] - self.dec[0]) * u.deg]


def parse_stencil(stencil_type: str, params: str) -> Stencil:
    """Convert a string stencil parameter to its internal representation."""
    if stencil_type == "POS":
        stencil_type, params = params.split(None, 1)

    if stencil_type == "CIRCLE":
        return CircleStencil.from_string(params)
    elif stencil_type == "POLYGON":
        return PolygonStencil.from_string(params)
    elif stencil_type == "RANGE":
        return RangeStencil.from_string(params)
    else:
        raise ValueError(f"Unknown stencil type {stencil_type}")
