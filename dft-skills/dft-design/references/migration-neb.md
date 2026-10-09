# Migration NEB Domain Contract

`migration-neb` is currently a design contract, not an operational workflow
backend. Record `initial_state`, `final_state`, `image_count` (at least three
intermediate images), `interpolation_method`, `climbing_image`, and
`force_threshold_eV_per_A` in `domain_metadata`.

Endpoints must be independently relaxed and traceable. A future workflow
adapter must review atom mapping, periodic-image choice, image interpolation,
spring settings, optimizer, tangent method, climbing-image activation, and the
exact force gate before submission. Do not classify a saddle point or migration
barrier until image forces and endpoint consistency are validated.
