---
name: brainstorm
description: 'Brainstorm + SWOT: generate ideas, then stress-test them.'
version: 1
author: user
license: MIT
metadata:
  hermes:
    tags:
    - workflow
    - brainstorm
    category: brainstorm
---
# Brainstorm + SWOT

User typed a topic/project after `/brainstorm`. Generate, then filter.

## How to run

1. **Generate**: 8-15 ideas, fast, no filter yet. Quantity > quality at this step.
2. **Cluster**: group by theme (2-5 clusters max).
3. **SWOT** the top cluster (or all, if small):
   - Strengths (intrinsic advantages)
   - Weaknesses (intrinsic limits)
   - Opportunities (extrinsic enablers)
   - Threats (extrinsic risks)
4. **Pick**: 1-3 candidates worth pursuing. Justify in one line each.
5. **Next step**: the smallest concrete action for each picked candidate.

## Output shape

```
# Brainstorm: <topic>

## Ideas
- ...

## Clusters
### <cluster>
- ...

## SWOT (top: <cluster>)
| S | W |
|---|---|
| ... | ... |
| **O** | **T** |
| ... | ... |

## Picks
1. <idea> — <one-line why>
   - Next: <concrete action>
```

No filler. Pick the ideas that survive their own SWOT row.
