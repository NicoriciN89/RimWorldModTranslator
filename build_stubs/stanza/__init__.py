"""Заглушка stanza для собранного .exe.

argostranslate/sbd.py делает безусловный `import stanza`, хотя при
ARGOS_CHUNK_TYPE=MINISBD (см. src/translator.py) Stanza-сегментатор никогда
не используется. Настоящая stanza тянет torch — ~370 МБ в сборке ради
импорта, который ни разу не вызывается. Этот стаб удовлетворяет импорт;
если кто-то явно переключит сегментатор на STANZA, он получит понятную
ошибку вместо тихого падения.
"""


class Pipeline:  # noqa: D101 — сигнатура повторяет stanza.Pipeline
    def __init__(self, *args, **kwargs):
        raise RuntimeError(
            "Stanza исключена из этой сборки для уменьшения размера "
            "(сегментация предложений выполняется через MiniSBD). "
            "Уберите переменную окружения ARGOS_CHUNK_TYPE=STANZA или "
            "запустите программу из исходников с установленной stanza."
        )
