from blinker import Signal


class Events:
    check_started = Signal()
    check_progress = Signal()
    check_completed = Signal()
    check_stopped = Signal()
    channel_checked = Signal()
    check_error = Signal()

    isp_detected = Signal()
    isp_mismatch = Signal()

    theme_changed = Signal()
    source_loaded = Signal()
    export_completed = Signal()

    state_changed = Signal()
    status_message = Signal()

    m3u_server_started = Signal()
    m3u_server_stopped = Signal()
