# michi — Pattern-fit check (catálogo)

   - **Pattern-fit check (michi 2026-09-03, self-evolution).** Before
     sign-off, the agent must surface the design pattern(s) the change
     is fitting into. Default catalogue (add more via Reflect):
     - **DDD aggregate** — clustered entities with a single root,
       invariants enforced at the boundary. Fits when the change
       introduces or modifies a cluster of related state.
     - **Hexagonal (ports & adapters)** — domain at the centre,
       I/O at the edges. Fits when adding/removing an external
       integration (DB, API, queue, FS).
     - **Clean Architecture / use-case driven** — application
       services orchestrate domain logic. Fits when the change is
       a feature with a clear user-triggered flow.
     - **CQRS** — separate read/write models. Fits when the
       change has asymmetric read vs write needs.
     - **Event Sourcing** — state as a stream of events. Fits
       when audit/history/replay matters.
     - **Transaction Script** — single procedure per use case.
       Fits when the change is small and a domain model would be
       ceremony (default for one-commit features).
     - **Active Record** — model object owns its persistence.
       Fits in CRUD apps where simplicity > purity.
     - **Table Module** — one module per DB table. Fits in
       reporting/analytics where data shape dominates.
     Ask one free-text question: "Which pattern fits this change
     and why?" — not multi-choice. The answer updates the DP
     immediately (see `## Style` — clarify answers update the
     artefact in the same turn, not later).
