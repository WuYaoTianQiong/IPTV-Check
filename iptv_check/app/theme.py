class ThemeManager:
    _current = "litera"
    _available = ["litera", "darkly"]

    STYLES = {
        "primary_action": "primary",
        "danger_action": "danger",
        "success_action": "success",
        "warning_action": "warning",
        "info_action": "info",
        "secondary_action": "secondary",
        "primary_outline": "primary-outline",
        "secondary_outline": "secondary-outline",
        "success_toggle": "success",
        "info_toggle": "info",
        "link": "info",
    }

    FONTS = {
        "title": ("Microsoft YaHei", 14, "bold"),
        "subtitle": ("Microsoft YaHei", 12, "bold"),
        "body": ("Microsoft YaHei", 10),
        "small": ("Microsoft YaHei", 9),
        "tiny": ("Microsoft YaHei", 8),
        "step_title": ("Microsoft YaHei", 10, "bold"),
        "step_circle": ("Microsoft YaHei", 10, "bold"),
        "mono": ("Consolas", 10),
    }

    @classmethod
    def style(cls, semantic_name: str) -> dict:
        return {"bootstyle": cls.STYLES.get(semantic_name, "secondary")}

    @classmethod
    def font(cls, semantic_name: str) -> tuple:
        return cls.FONTS.get(semantic_name, cls.FONTS["body"])

    @classmethod
    def current(cls) -> str:
        return cls._current

    @classmethod
    def toggle(cls, root_style) -> str:
        if cls._current == "litera":
            cls._current = "darkly"
        else:
            cls._current = "litera"
        root_style.theme_use(cls._current)
        from iptv_check.infra.event_bus import Events
        Events.theme_changed.send(theme=cls._current)
        return cls._current
