from __future__ import annotations

from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from app.config import Settings
    from db.models import RawPost

ALLOWED_SUMMARY_STYLES = frozenset(
    {
        "concise",
        "analytical",
        "neutral",
        "breaking-news",
        "digest-style",
        "warm-overview",
        "premium-newsroom",
    }
)


def normalize_summary_style(raw: str) -> str:
    k = raw.strip().lower().replace("_", "-")
    return k if k in ALLOWED_SUMMARY_STYLES else "neutral"


ALLOWED_HEADLINE_MODES = frozenset({"none", "json", "prefix"})


def normalize_headline_mode(raw: str) -> str:
    k = raw.strip().lower()
    return k if k in ALLOWED_HEADLINE_MODES else "none"


def digest_prompt_active(settings: Settings, cluster: list[RawPost]) -> bool:
    from scheduler.precluster import avg_pairwise_lexical_cohesion

    if not settings.digest_multi_post_enabled or len(cluster) < 2:
        return False
    cohesion = avg_pairwise_lexical_cohesion(cluster)
    return cohesion < settings.digest_cohesion_trigger_below


def build_system_prompt(
    settings: Settings,
    *,
    source_language: str = "ru",
    output_language: str = "ru",
) -> str:
    from app.editorial.source_languages import LANG_ZH, requires_translation

    style = settings.summary_style
    translate_block = ""
    if requires_translation(source_language, output_language):
        translate_block = (
            "Перевод и адаптация:\n"
            "* входные тексты могут быть на китайском (или другом языке) — итоговый post "
            f"должен быть **только на русском**;\n"
            "* переводи факты точно, без выдуманных деталей;\n"
            "* не оставляй иероглифы и фрагменты исходного языка в post;\n"
            "* имена собственные допускаются латиницей или общепринятой русской формой."
        )
        if source_language == LANG_ZH:
            translate_block += (
                "\n* китайский Telegram-канал: сохраняй нейтральный тон русскоязычного новостного канала."
            )

    blocks = [
        "Ты редактор Telegram-новостей.",
        "Работаешь как premium financial newsroom desk (Bloomberg/Reuters/FT-подход, адаптированный под Telegram).",
        "Тебе даны новости из разных Telegram-каналов.",
        "Найди записи, которые описывают ОДНО И ТО ЖЕ событие (одинаковые факты, одна история).",
        "Не объединяй разные темы и не смешивай несвязные новости.",
        "Если уверенности недостаточно или новости про разные события — не выдумывай связь.",
        "",
        _style_block_ru(style),
    ]
    if translate_block:
        blocks.extend(["", translate_block])
    blocks.extend(
        [
            "",
            "Строгие запреты:",
            "* не выдумывай факты, даты, числа, имена, места и цитаты — только то, что явно следует из входных текстов;",
            "* не добавляй «типичные» детали «наугад»;",
            "* если источники противоречат друг другу — явно укажи неопределённость и не угадывай, что верно;",
            "* не приписывай источникам формулировок, которых в данных нет.",
            "",
            "Формат поля post (для читателей канала):",
            "* первая строка — сильный hook без кликбейта, затем 2–6 коротких абзацев;",
            "* структура: hook → что произошло → почему это важно → влияние на рынок → краткий вывод;",
            "* используй конкретные цифры/уровни/проценты, если они есть во входных данных;",
            "* связный текст без маркированных списков вида «• [@channel] …»;",
            "* не указывай имена Telegram-каналов, @username, ссылки на источники и URL в тексте;",
            "* не обрывай мысль на «…» — доведи предложение до конца в пределах лимита;",
            "* визуальная чистота: короткие абзацы, легко сканируемый текст, без «стены»;",
        ]
    )
    if settings.editorial_safety_enabled:
        blocks.extend(
            [
                "",
                "Редакционная сдержанность:",
                "* избегай сенсационных и крикливых формулировок;",
                "* не делай категоричных выводов без опоры на цитаты/факты из входа;",
                "* без эмоциональных усилителей и кликбейта;",
                "* не преувеличивай значимость события.",
            "* tone of voice: уверенный, спокойный, институциональный, современный.",
            ]
        )
    blocks.extend(
        [
            "",
            "Правила:",
            "* только факты из входных текстов — не добавляй новых фактов и не домысливай;",
            "* если информации мало для корректного поста — честно укажи, что данных недостаточно;",
            "* до 1000 символов в поле post (если задан отдельный заголовок — он не входит в этот лимит);",
            "* тон канала: спокойный обзор мировых новостей, без паники и без токсичного позитива.",
        ]
    )
    return "\n".join(blocks)


def _style_block_ru(style: str) -> str:
    m = {
        "concise": "Стиль: максимально сжато, без воды, короткие фразы.",
        "analytical": "Стиль: аналитический — причины, контекст, связки между фактами; без оценочных ярлыков.",
        "neutral": "Стиль: нейтральный деловой язык без эмоциональной окраски.",
        "breaking-news": "Стиль: новостной — сначала суть и главный факт, затем детали; без сенсации и крика.",
        "digest-style": "Стиль: дайджест — можно структурировать 2–4 короткими абзацами или маркированными строками, если это помогает ясности.",
        "warm-overview": (
            "Стиль канала: доброжелательный обзор мировых новостей — факты чётко, тон ровный и слегка "
            "оптимистичный. Без крика, без пошлости и без навязчивого «всё хорошо». "
            "Заверши пост одной короткой репликой с умеренным нейтральным юмором, связанной с темой."
        ),
        "premium-newsroom": (
            "Стиль: premium financial newsroom для Telegram. Коротко, динамично, профессионально. "
            "Первый абзац должен цеплять фактом, далее давай контекст и market implications. "
            "Тон уверенный и аналитический, без дешевого кликбейта и без мемного жаргона."
        ),
    }
    return m.get(style, m["neutral"])


def build_user_prompt(
    settings: Settings,
    items_json: str,
    *,
    digest_active: bool,
    source_language: str = "ru",
    output_language: str = "ru",
) -> str:
    headline_rule = ""
    if settings.headline_mode == "json":
        headline_rule = (
            'Поле "headline": короткий заголовок (до ~120 символов), без кликбейта; '
            'поле "post": основной текст без дублирования заголовка дословно.'
        )
    elif settings.headline_mode == "prefix":
        headline_rule = (
            "Первая строка post — короткий заголовок (без markdown), вторая строка пустая, далее основной текст."
        )

    src_mentions = ""
    if settings.source_mentions_in_post:
        src_mentions = (
            "В конце post добавь одну строку «Источники: …» с перечислением каналов (как в данных), "
            "без выдуманных ссылок."
        )

    digest_block = ""
    if digest_active:
        digest_block = (
            "Режим дайджеста: входные материалы слабо связаны по лексике — не объединяй их в одну «историю». "
            "Сделай компактный дайджест: отдельный абзац на каждую тему (1–2 предложения), без @каналов и без списков; "
            "used_raw_post_ids перечисли все использованные id."
        )

    from app.editorial.source_languages import requires_translation

    lang_block = ""
    if requires_translation(source_language, output_language):
        lang_block = (
            f"Язык источника: {source_language}. Язык итогового post: {output_language} (строго). "
            "Переведи и адаптируй содержание; post не должен содержать иероглифы."
        )

    fmt_head = ""
    if settings.headline_mode == "json":
        fmt_head = ',\n  "headline": "короткий заголовок или пустая строка"'
    fmt_required = '"post", "used_raw_post_ids"'
    if settings.headline_mode == "json":
        fmt_required = '"post", "used_raw_post_ids", "headline"'

    return f"""Ниже список новостей в формате JSON. Каждый элемент содержит id, канал, id сообщения и текст.

Задача:
1) сгруппируй только те записи, которые описывают одно и то же событие (или следуй режиму дайджеста ниже);
2) если такой группы нет — верни пустой used_raw_post_ids и пустой post;
3) если группа есть — выбери только её и напиши итог;
4) верни СТРОГО один JSON-объект без markdown-ограждений (без ```), без текста до/после JSON.

Формат ответа (ровно эти поля):
{{
  "post": "текст итогового поста"{fmt_head},
  "used_raw_post_ids": [числа id записей, которые вошли в итог]
}}

Ограничения:
- used_raw_post_ids должен быть либо пустым массивом, либо содержать минимум 1 id;
- если post пустой, used_raw_post_ids должен быть пустым;
- post не длиннее 1000 символов;
- used_raw_post_ids должны быть подмножеством id из входных данных;
- не добавляй чисел, цитат и деталей, которых нет во входных текстовых полях;
- required JSON keys: {fmt_required}.

{headline_rule}
{src_mentions}

{lang_block}

{digest_block}

Входные данные:
{items_json}
"""


def compose_post_with_headline(settings: Settings, post: str, headline: str) -> str:
    h = (headline or "").strip()
    p = (post or "").strip()
    if settings.headline_mode != "json" or not h:
        return p
    if p.startswith(h):
        return p
    return f"{h}\n\n{p}"


def run_pipeline(
    text: str,
    summarizer: "BaseSummarizer | None" = None,
) -> dict[str, Any] | None:
    """
    Детерминированный smoke/integration путь без БД и Telegram.

    ``summarizer`` по умолчанию — ``FakeSummarizer`` (без сети). Для продакшена
    можно передать ``OpenAISummarizer`` (только вне активного asyncio-цикла).

    Возвращает ``summary`` (результат ``summarizer.summarize``) и ``quality_score``.
    Полный тик планировщика — ``scheduler.jobs.run_pipeline`` с ``PipelineContext``.
    """
    from ai.quality_score import compute_quality_scores
    from ai.summarizer import FakeSummarizer

    t = (text or "").strip()
    if not t:
        return None
    s = summarizer if summarizer is not None else FakeSummarizer()
    summary_text = s.summarize(t)
    return {
        "summary": summary_text,
        "quality_score": compute_quality_scores(
            post_text=summary_text,
            used_ids=[1],
            cluster_size=1,
        ),
    }
