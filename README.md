# AI Data Scientist Copilot

Local AI agent for product metric diagnosis, experiment evaluation, and business reporting.

## MVP: publishing-rate anomaly diagnosis

Question: **Why did publishing rate decline yesterday?**

The MVP will:

1. Query synthetic product-event data with DuckDB.
2. Compare a target day with a baseline period.
3. Decompose the change by country, user lifecycle, and platform.
4. Produce charts, evidence, and a business-facing report.
5. Use local `qwen2.5:7b` through Ollama to write the final summary.

## Planned stack

- Python 3.12
- DuckDB
- Pandas
- Plotly
- Streamlit
- Ollama (`qwen2.5:7b`)

## Project structure

```text
app/        Streamlit interface
src/        analysis and agent modules
data/       synthetic input data
reports/    generated charts and reports
tests/      automated tests
```

## Status

Project scaffold created. Next: create reproducible synthetic event data.
