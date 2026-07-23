# Tracked DGX transfer archives

`xerus_oqmd_cache_v3_full_20260722.tar.gz` is the frozen OQMD OPTIMADE cache
required by the Atomly-Core-100 XERUS run. It is committed as a small public
archive so the DGX only needs to pull this branch; no separate file transfer is
required.

- SHA-256: `77797b9d064fe8812d57ccf67f5cd17a3541c079b8d4809c71e4215b986e4fb8`
- Systems: 470/470 complete
- OPTIMADE pages: 478
- Globally unique OQMD structure IDs: 5,315
- Archive top-level directory: `oqmd_optimade_cache_v3_full/`

Verify with:

```bash
(cd fig4/benchmark/server_transfer && \
  sha256sum -c xerus_oqmd_cache_v3_full_20260722.tar.gz.sha256)
```

Extract into `fig4/benchmark/method_inputs/` as directed by
`fig4/benchmark/DGX_NEXT_TASK.md`. Do not commit the extracted cache, MongoDB
volume, API credentials, or private benchmark truth.
