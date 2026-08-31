# License notice — AGPL-3.0 coupling

The code in this directory imports and builds on the MiroFish engine at
`vibemind-os/spaces/mirofish/mirofish/`, which is licensed under the
**GNU AGPL-3.0** (upstream chain: 666ghj/MiroFish → nikmcfly/MiroFish-Offline;
simulation engine camel-ai/oasis). It is therefore a derivative of AGPL code
and is distributed under **AGPL-3.0**, not under the repository's root MIT
license.

Practical consequences:

- If you run this code as part of a network service, AGPL §13 requires
  offering its source to users of that service.
- Do not copy code from this directory into MIT-licensed parts of the
  repository.
- The rest of `spaces/marketing/` does not import MiroFish and remains under
  the root MIT license.

See `THIRD_PARTY.md` in the repository root for the full license inventory.
