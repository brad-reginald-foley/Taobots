from __future__ import annotations

import uuid

from body_parts import BodyPart, LegPart


class BodyFactory:
    """Instantiates body parts from spec dicts, assigning stable UUID part IDs.

    Dispatches on spec["type"]. Currently supports "leg"; meridian, armor, and
    neuron will be added as each organ type is wired in subsequent phases.
    """

    @staticmethod
    def make_parts(specs: list[dict]) -> list[BodyPart]:
        parts: list[BodyPart] = []
        for spec in specs:
            part_type = spec["type"]
            part_id = str(uuid.uuid4())
            if part_type == "leg":
                parts.append(LegPart(
                    part_id=part_id,
                    r=float(spec["r"]),
                    theta=float(spec["theta"]),
                    phi=float(spec.get("phi", 0.0)),
                    max_thrust=float(spec["max_thrust"]),
                    capacity=float(spec["capacity"]),
                    drain_max=float(spec["drain_max"]),
                ))
            else:
                raise ValueError(f"Unknown body part type: {part_type!r}")
        return parts
