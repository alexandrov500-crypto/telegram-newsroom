# OpenAI degraded

## Symptoms

- `/health` → openai `degraded` or circuit `open`
- Fallback drafts (no GPT polish)
- `openai_circuit_open` metric

## Diagnosis

```bash
curl -s http://127.0.0.1:8080/health | python3 -m json.tool
grep openai_circuit logs/local-run.log | tail -10
```

## Fix

1. Verify `OPENAI_API_KEY` and billing
2. Wait for circuit half-open (default ~5 min)
3. Pipeline continues with `fallback_summarizer` — **do not restart loop**

## Maintenance

If sustained outage >1h:

```bash
bash scripts/newsroom maintenance on --reason openai_outage
```

Publishing pauses; drafts still generated. Clear with `maintenance off` when API recovers.
