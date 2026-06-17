# Layout Archetypes

Use this file to prevent free-coordinate slide construction. Every ordinary content slide must choose one declared layout archetype before generator code is written, unless the user explicitly requests a custom layout.

## Mandatory Rules

1. Pick one layout archetype before placing slide objects.
2. Declare all high-level objects in a layout box table before writing PPTX code.
3. High-level boxes must not overlap. Child objects inside the