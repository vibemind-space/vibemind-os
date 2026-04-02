---
name: requirements-enrichment
description: Transform abstract requirements into technical specifications
tier_tokens:
  minimal: 100
  standard: 250
  full: 500
---

# Requirements Enrichment

## Purpose
Transform abstract, business-level requirements into detailed technical specifications.

## Input
Abstract requirement like:
```json
{"id": "REQ-001", "title": "GPS-Integration", "text": "Kontinuierliche Positionsübermittlung"}
```

## Output
Enriched requirement with tech specs:
```json
{
  "id": "REQ-001",
  "title": "GPS-Integration",
  "tech_spec": {
    "database": {"type": "PostgreSQL", "tables": ["positions"], "extension": "PostGIS"},
    "api": {"type": "REST+WebSocket", "endpoints": ["POST /positions", "WS /stream"]},
    "frontend": {"components": ["MapView"], "libraries": ["mapbox-gl"]}
  }
}
```

## MUST
- Identify ALL technical needs (database, API, frontend)
- Be SPECIFIC with table names, field types, endpoints
- Determine complexity level (low/medium/high)
- Identify dependencies between requirements

## MUST NOT
- Leave any requirement without tech_spec
- Use placeholder names like "TBD" or "TODO"
- Ignore real-time needs (WebSocket when appropriate)
- Miss database requirements for data-heavy features

<!-- END_TIER_MINIMAL -->

## Analysis Patterns

### Database Triggers
| Keyword | Database Need |
|---------|--------------|
| track, monitor, log | Time-series table with timestamps |
| location, GPS, position | Geo table with PostGIS |
| history, audit | Versioned table or audit log |
| search, filter | Indexed columns |
| relate, link | Foreign key relation |

### API Triggers
| Keyword | API Need |
|---------|----------|
| real-time, live, stream | WebSocket endpoint |
| list, search, filter | GET with query params |
| create, add, submit | POST endpoint |
| update, edit, modify | PUT/PATCH endpoint |
| delete, remove | DELETE endpoint |
| upload, attach | multipart/form-data |

### Frontend Triggers
| Keyword | Frontend Need |
|---------|--------------|
| map, location | MapView + mapbox-gl |
| chart, graph, analytics | Dashboard + recharts |
| form, input, submit | Form component + validation |
| list, table, grid | DataTable component |
| upload, attach | FileUpload component |

<!-- END_TIER_STANDARD -->

## Complex Patterns

### Multi-Entity Requirements
When a requirement mentions multiple entities:
1. Create separate database tables
2. Define relations (1:N, N:M)
3. Create separate API resources
4. Consider join/aggregate endpoints

### Real-Time Requirements
For live/streaming features:
1. REST for CRUD operations
2. WebSocket for live updates
3. Event types for different updates
4. Reconnection handling

### Geo/Location Requirements
For location-based features:
1. PostGIS extension
2. GEOGRAPHY/GEOMETRY types
3. Spatial indexes
4. Distance/boundary queries
