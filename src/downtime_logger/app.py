"""
Application controller. Glues together: config -> storage -> metric ->
state machine -> detectors (in QThreads) -> UI (main window + popup + tray).

Ownership rules:
* state machine and storage live on the main (Qt GUI) thread.
* each detector lives on its own QThread, owned by this controller.
* persisting reading logs is opt-in (storage.log_readings is called on
  every recompute, but a future flag can disable it for high-rate setups).
"""
from __future__ import annotations

import logging
from typing import Optional

from PySide6.QtCore import Qt, QMetaObject, QObject, QThread, Slot
from PySide6.QtWidgets import QApplication

from .config import AppConfig, DetectorSpec
from .core.event import DowntimeEvent
from .core.metric import Metric
from .core.plugin_loader import instantiate
from .core.state_machine import StateMachine
from .detectors.base import Detector
from .storage.base import StorageBackend
from .ui.main_window import MainWindow
from .ui.popup_dialog import NewEventPopup
from .ui.tray import TrayIcon
from .web.server import WebServer
from .web.snapshot import SnapshotStore

log = logging.getLogger(__name__)


class Controller(QObject):
    def __init__(self, config: AppConfig, app: QApplication) -> None:
        super().__init__()
        self._app = app

        # --- storage ----------------------------------------------------
        self._storage: StorageBackend = instantiate(
            config.storage.plugin, **config.storage.options
        )

        # --- metric + state machine -------------------------------------
        # debounce_seconds is consumed by the StateMachine, not the metric;
        # strip it out before passing the rest to the metric constructor.
        metric_opts = dict(config.metric.options)
        debounce = float(metric_opts.pop("debounce_seconds", 5.0))
        metric: Metric = instantiate(config.metric.plugin, **metric_opts)
        self._sm = StateMachine(metric=metric, debounce_seconds=debounce)

        # --- detectors (each on its own thread) -------------------------
        self._threads: list[QThread] = []
        self._detectors: list[Detector] = []
        for spec in config.detectors:
            self._spawn_detector(spec)

        # --- snapshot + optional web server -----------------------------
        self._snapshot = SnapshotStore()
        self._web: Optional[WebServer] = None
        if config.webserver.enabled:
            self._web = WebServer(
                snapshot=self._snapshot,
                storage=self._storage,
                bind=config.webserver.bind,
                port=config.webserver.port,
                refresh_seconds=config.webserver.refresh_seconds,
                history_limit=config.webserver.history_limit,
            )
            self._web.start()

        # --- UI ---------------------------------------------------------
        self._window = MainWindow()
        self._popup: Optional[NewEventPopup] = None
        self._tray = TrayIcon(
            on_show=self._show_window,
            on_quit=self._quit,
            on_toggle_enabled=self._sm.set_enabled,
        )
        self._tray.show()

        # --- wiring -----------------------------------------------------
        self._sm.readings_changed.connect(self._window.status.on_readings)
        self._sm.score_changed.connect(self._window.status.on_score)
        self._sm.score_changed.connect(self._tray.on_score)
        self._sm.readings_changed.connect(self._on_readings_log)
        self._sm.readings_changed.connect(self._snapshot.update_readings)
        self._sm.score_changed.connect(self._snapshot.update_score)
        self._sm.event_opened.connect(self._on_event_opened)
        self._sm.event_closed.connect(self._on_event_closed)

        self._window.event_save_requested.connect(self._on_event_save)
        self._window.event_create_requested.connect(self._on_event_create)
        self._window.refresh_requested.connect(self._refresh_history)
        self._window.manual_end_requested.connect(self._on_manual_end)
        self._window.events_delete_requested.connect(self._on_events_delete)
        self._window.enabled_toggled.connect(self._sm.set_enabled)
        self._sm.enabled_changed.connect(self._window.set_enabled_mode)
        self._sm.enabled_changed.connect(self._tray.set_enabled_mode)
        # Default state is disabled; reflect it in the UI now.
        self._window.set_enabled_mode(self._sm.enabled)
        self._tray.set_enabled_mode(self._sm.enabled)

        self._refresh_history()
        self._window.show()

        # Catch any quit path (Cmd-Q on macOS, dock close, programmatic
        # app.quit()) so worker threads are always stopped cleanly. Without
        # this, ~QThread fires while the worker is still running and aborts.
        self._cleaned_up = False
        app.aboutToQuit.connect(self._cleanup)

    # --- detector lifecycle ---------------------------------------------

    def _spawn_detector(self, spec: DetectorSpec) -> None:
        det: Detector = instantiate(spec.plugin, detector_id=spec.id, **spec.options)
        self._sm.register_detector(spec.id, spec.weight)

        thread = QThread()
        thread.setObjectName(f"detector-{spec.id}")
        det.moveToThread(thread)
        # Force queued so state_changed always lands on the main (Qt GUI)
        # thread; the state machine's debounce QTimer lives there and
        # cannot be manipulated from a worker thread (macOS will SIGABRT).
        det.state_changed.connect(
            self._sm.on_state_changed, Qt.ConnectionType.QueuedConnection
        )
        thread.finished.connect(det.stop, Qt.ConnectionType.DirectConnection)
        self._threads.append(thread)
        self._detectors.append(det)
        thread.start()
        # PySide6's connect to thread.started runs the slot on the main
        # thread, which gives any QTimer/QSocketNotifier created inside
        # start() the wrong (main) affinity. Explicitly queue start onto
        # the detector's worker thread once the thread has spun up.
        QMetaObject.invokeMethod(
            det, "start", Qt.ConnectionType.QueuedConnection
        )
        log.info("started detector %s (%s, weight=%.2f)",
                 spec.id, spec.plugin, spec.weight)

    # --- state-machine slots --------------------------------------------

    @Slot(dict)
    def _on_readings_log(self, _readings) -> None:
        # log every recompute — cheap on SQLite, useful for post-mortems.
        try:
            self._storage.log_readings(self._sm.last_score, self._sm.readings.values())
        except Exception:
            log.exception("storage.log_readings failed")

    @Slot(object)
    def _on_event_opened(self, event: DowntimeEvent) -> None:
        try:
            self._storage.open_event(event)
        except Exception:
            log.exception("storage.open_event failed")
        self._snapshot.set_current_event(event)

        if self._popup is not None:
            self._popup.close()
        self._popup = NewEventPopup(event)
        self._popup.saved.connect(self._on_event_save)
        self._popup.show()
        self._popup.raise_()
        self._popup.activateWindow()
        self._refresh_history()

    @Slot(object)
    def _on_event_closed(self, event: DowntimeEvent) -> None:
        try:
            self._storage.close_event(event)
        except Exception:
            log.exception("storage.close_event failed")
        self._snapshot.set_current_event(None)

        if self._popup is not None:
            self._popup.update_running_event(event)
        self._refresh_history()

    @Slot(object)
    def _on_event_save(self, event: DowntimeEvent) -> None:
        sm_event = self._sm.current_event
        is_active = (
            sm_event is not None and event.id is not None
            and sm_event.id == event.id
        )
        if is_active and event.ended_at is not None:
            self._sm.close_current_event(event.ended_at)
        try:
            self._storage.update_event(event)
        except Exception:
            log.exception("storage.update_event failed")
        self._refresh_history()

    @Slot(object)
    def _on_event_create(self, event: DowntimeEvent) -> None:
        if not event.opened_by:
            event.opened_by = "manual"
        try:
            self._storage.open_event(event)
        except Exception:
            log.exception("storage.open_event (manual) failed")
            return
        log.info("Manual downtime event created (id=%s)", event.id)
        self._refresh_history()

    @Slot(int)
    def _on_manual_end(self, event_id: int) -> None:
        sm_event = self._sm.current_event
        if sm_event is None or sm_event.id != event_id:
            log.warning("manual end requested for non-active event %s", event_id)
            return
        self._sm.close_current_event()

    @Slot(list)
    def _on_events_delete(self, event_ids: list[int]) -> None:
        sm_event = self._sm.current_event
        active_cleared = False
        for event_id in event_ids:
            if sm_event is not None and sm_event.id == event_id:
                # Detach the SM from the row before we drop it so a later
                # recovery doesn't try to update a deleted id.
                self._sm.close_current_event()
                if self._popup is not None:
                    self._popup.close()
                    self._popup = None
                sm_event = None
                active_cleared = True
            try:
                deleted = self._storage.delete_event(event_id)
            except Exception:
                log.exception("storage.delete_event failed for id=%s", event_id)
                deleted = False
            if deleted:
                log.warning("Downtime event #%s permanently deleted", event_id)
        if active_cleared:
            self._snapshot.set_current_event(None)
        self._refresh_history()

    @Slot()
    def _refresh_history(self) -> None:
        try:
            events = self._storage.list_events()
        except Exception:
            log.exception("storage.list_events failed")
            events = []
        self._window.set_events(events)

    # --- tray actions ----------------------------------------------------

    @Slot()
    def _show_window(self) -> None:
        self._window.show()
        self._window.raise_()
        self._window.activateWindow()

    @Slot()
    def _quit(self) -> None:
        # Tray "Quit" path. The actual cleanup runs via app.aboutToQuit so
        # all quit paths (tray, Cmd-Q, dock close) converge through it.
        self._app.quit()

    @Slot()
    def _cleanup(self) -> None:
        if self._cleaned_up:
            return
        self._cleaned_up = True
        if self._web is not None:
            try:
                self._web.stop()
            except Exception:
                log.exception("web server stop failed")
        for t in self._threads:
            t.quit()
        for t in self._threads:
            if not t.wait(2000):
                log.warning("thread %s did not exit within 2s", t.objectName())
        try:
            self._storage.close()
        except Exception:
            pass
