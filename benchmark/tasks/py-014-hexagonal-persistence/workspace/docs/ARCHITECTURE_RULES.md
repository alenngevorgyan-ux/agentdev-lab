# Architecture rules

The service is organised as ports and adapters. Dependencies point inward.

```
infrastructure  ->  application  ->  domain
```

1. `src/domain` is the innermost layer. It may import only the standard
   library and other `src.domain` modules. It must never import from
   `src.application` or `src.infrastructure`.
2. `src/application` orchestrates use cases. It may import from `src.domain`
   and the standard library. It must never import from `src.infrastructure`.
3. `src/infrastructure` holds adapters: databases, queues, files, HTTP. It may
   import from any layer.
4. A use case never constructs its own adapter. Adapters are passed in.
5. Ports are declared in the domain as abstract classes; adapters implement
   them in infrastructure.

These rules are enforced by an automated import-graph test.
