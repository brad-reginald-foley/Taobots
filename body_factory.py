from __future__ import annotations

from body_parts import DEFAULT_LEG_MASS, BodyPart, LegPart
from rng import derive_token


class BodyFactory:
    """Instantiates body parts from spec dicts, assigning deterministic part IDs.

    Dispatches on spec["type"]. Currently supports "leg"; meridian, armor, and
    neuron will be added as each organ type is wired in subsequent phases.

    Part ids are derived, never random (`AD-9`). `uuid4()` draws from `os.urandom`,
    which no seed can reach, so a random part id breaks reproducibility the moment it
    reaches a log, a state hash or an iteration order (`AD-12`).
    """

    @staticmethod
    def gene_id(spec: dict, spec_index: int) -> str:
        """The genome-space id of one body-spec entry.

        Gene ids and part ids are separate spaces that are never collapsed (`AD-9`):
        a gene is declarable and persists in a genome, a part is what expressing that
        gene produced. Body specs are hand-written stand-ins for a genome and do not
        carry ids yet, so a spec may declare one with an `"id"` key and otherwise
        falls back to its position in the list. Positional ids are stable for a given
        spec list — which is all today's fixed `DEFAULT_PARAMS["body"]` needs — but
        reordering the list renames the genes, so genomes will declare `"id"`."""
        declared = spec.get("id")
        if declared is not None:
            return str(declared)
        return f"{spec.get('type', 'part')}[{spec_index}]"

    @staticmethod
    def make_parts(
        specs: list[dict], *, run_seed: int, owner_id: int | str
    ) -> list[BodyPart]:
        """Express `specs` into parts, deriving each `part_id` from the run seed.

        `part_id` is derived from `(run_seed, owner_id, gene_id, expression_index)`.
        The first three are `AD-9`'s tuple; `owner_id` is the organism the parts are
        being expressed for, without which every bot sharing a body spec in one run
        would be handed identical part ids. Expression is one-to-many (`BODY-6`), so
        the index distinguishes the several parts one gene will later produce; today
        each spec expresses exactly one part, so it is always 0.

        `owner_id` is required and has no default on purpose: a default would be a
        single value every direct caller silently shared, which is the id collision
        this argument exists to prevent, reintroduced as a convenience.

        Same seed and same owner ⇒ same ids, every run, every process."""
        parts: list[BodyPart] = []
        seen_genes: dict[str, int] = {}
        for spec_index, spec in enumerate(specs):
            part_type = spec["type"]
            gene = BodyFactory.gene_id(spec, spec_index)
            if gene in seen_genes:
                # Two genes with one id express to one part id, so the second part
                # would overwrite the first in any id-keyed structure. Declared ids and
                # the positional fallback share a namespace, so `{"id": "leg[0]"}` can
                # collide with the spec that happens to sit at index 0; and because ids
                # are stringified, `1` and `"1"` are the same gene here.
                raise ValueError(
                    f"duplicate gene id {gene!r}: body spec {spec_index} collides with "
                    f"spec {seen_genes[gene]}. Gene ids must be unique within a body — "
                    f"declared ids share a namespace with the positional fallback "
                    f"'type[index]', and are compared as text, so 1 and '1' collide."
                )
            seen_genes[gene] = spec_index
            expression_index = 0
            part_id = derive_token(run_seed, "part", owner_id, gene, expression_index)
            if part_type == "leg":
                parts.append(LegPart(
                    part_id=part_id,
                    r=float(spec["r"]),
                    theta=float(spec["theta"]),
                    phi=float(spec.get("phi", 0.0)),
                    max_thrust=float(spec["max_thrust"]),
                    capacity=float(spec["capacity"]),
                    drain_max=float(spec["drain_max"]),
                    # Defaulted rather than required: `mass` is a trait a genome will
                    # carry, and hand-written specs (tests, sandboxes) predate it.
                    # The shipped body spec states it explicitly all the same, so the
                    # value a run actually uses is visible where the other traits are.
                    mass=float(spec.get("mass", DEFAULT_LEG_MASS)),
                ))
            else:
                raise ValueError(f"Unknown body part type: {part_type!r}")
        return parts
