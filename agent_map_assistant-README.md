# Agent Map Assistant (Python)

Python port of the Qt `AgentMapAssistant` example. Ask for map operations in plain
language ("Show the buildings within 150 m of a school in red") and watch them run as a
validated, previewed and recorded GeoKernel workflow. The planner (an LLM, or the offline
demo) only proposes a **workflow DSL v2** plan (ADR-0007); GeoKernel validates it, the
plan is shown before anything runs, steps that change data need your confirmation of
that exact plan, and every executed workflow can be undone and is recorded with
hash-chained provenance.

The window is PySide6 with the native GeoKernel 2D viewer embedded; the chat panel is
plain PySide6 on top of `geokernel.agent.GisAgent` (evaluate, run, undo, provenance)
and `geokernel.agent.propose` (LLM call on a worker thread).

## Requirements and run

Needs a **geokernel package with the agent API (newer than 1.5.40)**, PySide6 6.11,
Windows x64 and a valid GeoKernel license. Until that release is on PyPI, use the
`GeoKernel.Python` sources and a GeoKernel runtime built from source:

```powershell
$env:PYTHONPATH = "D:\projects\GeoKernel.Python\src"
$env:GEOKERNEL_BIN = "D:\projects\GeoKernel\outputs\build\Release"
python agent_map_assistant.py
```

With geokernel 1.5.40 or earlier the example exits with a message that the agent API
is missing.

### Planner: offline demo or an LLM

Without configuration the example runs in **offline demo mode**: the six requests in
the **Try** list have prepared plans in
[agent_map_assistant-data/agent-demo.json](agent_map_assistant-data/agent-demo.json),
exactly as a model would return them, and they go through the same validation, preview,
confirmation, execution, undo and provenance. Other requests are answered with how to
enable a model. No network access is needed.

To plan your own requests, set the provider before starting:

| Provider | Environment |
|---|---|
| Anthropic | `GEOKERNEL_LLM_PROVIDER=anthropic`, `ANTHROPIC_API_KEY` (model defaults to `claude-opus-5-5`) |
| OpenAI | `GEOKERNEL_LLM_PROVIDER=openai`, `GEOKERNEL_LLM_MODEL`, `OPENAI_API_KEY` |
| Ollama (local) | `GEOKERNEL_LLM_PROVIDER=ollama`, `GEOKERNEL_LLM_MODEL`, optional `GEOKERNEL_LLM_BASE_URL` |

Keys are read by the native code when a request is made and never appear in the log,
errors or provenance. The model receives the request, the layer list with field names
and the field notes from `agent-demo.json` — no feature data.

## Workflow

1. The map shows a synthetic neighbourhood: 352 buildings (`ref`, `use`, `floors`,
   `year_built`, `status`), 4 schools, 3 parks and 16 streets.
2. Pick a request under **Try** and click **Ask**, or type one and click **Send**.
3. The **Plan** box lists every step with its category, effects and parameters before
   anything runs. A plan that fails validation is rejected with the reason.
4. **Run** executes read-only and view-only plans. Plans that change or delete data show
   **Confirm and run**, which passes that plan's `planId` as the confirmation.
5. The log shows results: tables row by row, measurements with units, feature counts.
6. **Undo last** reverts every step of the most recent workflow.
7. **Provenance...** shows the hash-chained execution records.

The six sample requests, their plans and which ones need confirmation are listed in the
Qt example's README. Edits only apply to result layers in memory; the GeoJSON files are
never modified.

## Data

`agent_map_assistant-data/*.geojson` is a synthetic, deterministic neighbourhood shared
with the Qt, .NET, Electron and Rust versions (street names borrowed from Kadıköy,
Istanbul; geometry and attributes invented).
