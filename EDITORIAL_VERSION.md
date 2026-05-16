# Telegram AI Newsroom — редакционная версия (снимок)

**Дата снимка:** 2026-05-12  
**Назначение:** зафиксировать последнюю доработку MVP под редакционное качество после soak (архитектура и инфраструктура без смены стека).

## Ключевые изменения

1. **Стили саммари** — `SUMMARY_STYLE`: `concise`, `analytical`, `neutral`, `breaking-news`, `digest-style` (промпты в `ai/editorial.py`).
2. **Редакционная безопасность** — `EDITORIAL_SAFETY=true|false` (доп. ограничения в system prompt).
3. **Источники** — дедуп по `(channel, message_id)`; опционально строка «Источники: …» в тексте (`SOURCE_MENTIONS_IN_POST`); разметка всех raw-строк кластера с теми же парами как `processed` (`scheduler/jobs.py`).
4. **Pre-cluster** — `CLUSTER_MIN_LEXICAL_JACCARD`, `CLUSTER_MIN_PAIR_LAST_JACCARD`, `PRECLUSTER_TRIM_BUCKET_MULTIPLIER`; cohesion `avg_pairwise_lexical_cohesion` в `scheduler/precluster.py`.
5. **Оценка качества** — `ai/quality_score.py` + логи `quality.score.*` / предупреждения (`QUALITY_SCORING_ENABLED`); пайплайн не блокируется.
6. **Заголовки** — `HEADLINE_MODE`: `none` | `json` | `prefix` (`app/schemas.py`, `ai/cluster_summarizer.py`).
7. **Мульти-пост дайджест** — `DIGEST_MULTI_POST` + `DIGEST_COHESION_TRIGGER_BELOW` (режим в user prompt при низкой связности).
8. **Наблюдаемость** — скользящие `editorial_*` в `ops.report.summary`, `quality.warn.duplicate_summary_pattern` (`utils/observability.py`).
9. **Конфиг** — `app/config.py`, проверки `app/startup_validation.py`, примеры в `.env.example`, раздел в `README.md`.
10. **Summarizer DI** — `BaseSummarizer` / `FakeSummarizer` / `OpenAISummarizer` в `ai/summarizer.py`; JSON-кластер в `ai/cluster_summarizer.py`; общее исключение `SummarizerError` в `ai/exceptions.py`; `run_pipeline(text, summarizer=None)` в `ai/editorial.py` по умолчанию использует `FakeSummarizer`.

## Исправление

- Удалён ошибочный `raise` после блока `async with lock` в `scheduler/jobs.py` (`run_pipeline`).

## Файлы (ориентир)

| Область | Путь |
|--------|------|
| Промпты и стили | `ai/editorial.py` |
| Summarizer (фасад, fake, text OpenAI) | `ai/summarizer.py` |
| JSON-кластер OpenAI (как раньше) | `ai/cluster_summarizer.py` |
| Исключение кластера | `ai/exceptions.py` |
| Оценки | `ai/quality_score.py`, `ai/summary_quality.py` |
| Кластер | `scheduler/precluster.py` |
| Пайплайн | `scheduler/jobs.py` |
| Схема ответа | `app/schemas.py` |
| Настройки | `app/config.py` |
| Метрики/отчёт | `utils/observability.py` |

## Примечание

Статичный `ai/prompts.py` в пайплайне не используется; актуальные формулировки собираются в `ai/editorial.py`.
