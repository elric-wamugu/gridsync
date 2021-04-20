# -*- coding: utf-8 -*-
from datetime import datetime, timedelta

from humanize import naturalsize
from PyQt5.QtCore import QSize, Qt
from PyQt5.QtCore import pyqtSlot as Slot
from PyQt5.QtGui import QIcon, QMovie
from PyQt5.QtWidgets import (
    QAction,
    QGridLayout,
    QLabel,
    QSizePolicy,
    QSpacerItem,
    QToolButton,
    QWidget,
)

from gridsync import resource

# from gridsync.gui.charts import ZKAPCompactPieChartView
from gridsync.gui.color import BlendedColor
from gridsync.gui.font import Font
from gridsync.gui.menu import Menu
from gridsync.gui.pixmap import Pixmap


class StatusPanel(QWidget):
    def __init__(self, gateway, gui):
        super().__init__()
        self.gateway = gateway
        self.gui = gui

        self.state = 0
        self.num_connected = 0
        self.num_known = 0
        self.available_space = 0

        self.checkmark_icon = QLabel()
        self.checkmark_icon.setPixmap(Pixmap("checkmark.png", 20))

        self.syncing_icon = QLabel()

        self.sync_movie = QMovie(resource("sync.gif"))
        self.sync_movie.setCacheMode(True)
        self.sync_movie.updated.connect(
            lambda: self.syncing_icon.setPixmap(
                self.sync_movie.currentPixmap().scaled(
                    20, 20, Qt.KeepAspectRatio, Qt.SmoothTransformation
                )
            )
        )

        self.status_label = QLabel()
        p = self.palette()
        dimmer_grey = BlendedColor(
            p.windowText().color(), p.window().color(), 0.6
        ).name()
        self.status_label.setStyleSheet(f"QLabel {{ color: {dimmer_grey} }}")
        self.status_label.setFont(Font(10))

        self.setMaximumHeight(32)

        self.setStyleSheet("QToolButton { border: none }")
        # self.setStyleSheet("""
        #    QToolButton { color: dimgrey; border: none; }
        #    QToolButton:hover {
        #        background-color: #FAFAFA;
        #        border: 1px solid grey;
        #        border-radius: 2px;
        #    }
        # """)

        self.tor_button = QToolButton()
        self.tor_button.setIconSize(QSize(20, 20))
        self.tor_action = QAction(
            QIcon(resource("tor-onion.png")),
            "This connection is being routed through the Tor network",
        )
        self.tor_button.setDefaultAction(self.tor_action)
        self.tor_button.setStyleSheet("QToolButton { border: none }")
        if not self.gateway.use_tor:
            self.tor_button.hide()

        preferences_button = QToolButton(self)
        preferences_button.setIcon(QIcon(resource("preferences.png")))
        preferences_button.setIconSize(QSize(20, 20))
        preferences_button.setMenu(Menu(self.gui, show_open_action=False))
        preferences_button.setPopupMode(2)
        preferences_button.setStyleSheet(
            "QToolButton { border: none }"
            "QToolButton::menu-indicator { image: none }"
        )

        # zkap_chart_view = ZKAPCompactPieChartView()

        # self.zkap_label = QLabel()
        # self.zkap_label.setStyleSheet(f"color: {dimmer_grey}")
        # self.zkap_label.hide()

        self.stored_label = QLabel()
        self.stored_label.setStyleSheet(f"color: {dimmer_grey}")
        self.stored_label.hide()

        self.expires_label = QLabel()
        self.expires_label.setStyleSheet(f"color: {dimmer_grey}")
        self.expires_label.hide()

        layout = QGridLayout(self)
        left, _, right, bottom = layout.getContentsMargins()
        layout.setContentsMargins(left, 0, right, bottom - 2)
        layout.addWidget(self.checkmark_icon, 1, 1)
        layout.addWidget(self.syncing_icon, 1, 1)
        layout.addWidget(self.status_label, 1, 2)
        layout.addItem(QSpacerItem(0, 0, QSizePolicy.Expanding, 0), 1, 3)
        # layout.addWidget(zkap_chart_view, 1, 5)
        # layout.addWidget(self.zkap_label, 1, 5)
        layout.addWidget(self.stored_label, 1, 6)
        layout.addWidget(self.expires_label, 1, 7)
        layout.addWidget(self.tor_button, 1, 8)
        layout.addWidget(preferences_button, 1, 9)

        self.gateway.monitor.total_sync_state_updated.connect(
            self.on_sync_state_updated
        )
        self.gateway.monitor.space_updated.connect(self.on_space_updated)
        self.gateway.monitor.nodes_updated.connect(self.on_nodes_updated)
        # self.gateway.monitor.zkaps_updated.connect(self.on_zkaps_updated)
        self.gateway.monitor.total_folders_size_updated.connect(
            self.on_total_folders_size_updated
        )
        self.gateway.monitor.days_remaining_updated.connect(
            self.on_days_remaining_updated
        )

        self.on_sync_state_updated(0)

    def _update_status_label(self):
        if self.state == 0:
            if self.gateway.shares_happy:
                if self.num_connected < self.gateway.shares_happy:
                    self.status_label.setText(
                        f"Connecting to {self.gateway.name} ("
                        f"{self.num_connected}/{self.gateway.shares_happy})..."
                    )
                else:
                    self.status_label.setText(
                        f"Connected to {self.gateway.name}"
                    )

            else:
                self.status_label.setText(
                    f"Connecting to {self.gateway.name}..."
                )
            self.sync_movie.setPaused(True)
            self.syncing_icon.hide()
            self.checkmark_icon.hide()
        elif self.state == 1:
            self.status_label.setText("Syncing")
            self.checkmark_icon.hide()
            self.syncing_icon.show()
            self.sync_movie.setPaused(False)
        elif self.state == 2:
            self.status_label.setText("Up to date")
            self.sync_movie.setPaused(True)
            self.syncing_icon.hide()
            self.checkmark_icon.show()
        if self.available_space:
            self.status_label.setToolTip(
                "Connected to {} of {} storage nodes\n{} available".format(
                    self.num_connected, self.num_known, self.available_space
                )
            )
        else:
            self.status_label.setToolTip(
                "Connected to {} of {} storage nodes".format(
                    self.num_connected, self.num_known
                )
            )

    def on_sync_state_updated(self, state):
        self.state = state
        self._update_status_label()

    def on_space_updated(self, space):
        self.available_space = naturalsize(space)
        self._update_status_label()

    def on_nodes_updated(self, connected, known):
        self.num_connected = connected
        self.num_known = known
        self._update_status_label()

    # @Slot(int, int)
    # def on_zkaps_updated(self, used: int, remaining: int) -> None:
    #    total = used + remaining
    #    self.zkap_label.setToolTip(
    #        f"{self.gateway.zkapauthorizer.zkap_name}s:\n\nUsed: {used}\n"
    #        f"Total: {total}\nAvailable: {remaining}"
    #    )
    #    if remaining and remaining >= 1000:
    #        remaining = str(round(remaining / 1000, 1)) + "k"  # type: ignore
    #    self.zkap_label.setText(
    #        f"{self.gateway.zkapauthorizer.zkap_name_abbrev}s "
    #        f"available: {remaining} "
    #    )
    #    self.zkap_label.show()

    @Slot(object)
    def on_total_folders_size_updated(self, size: int) -> None:
        if self.expires_label.text():
            self.stored_label.setText(f"Stored: {naturalsize(size)},")
        else:
            self.stored_label.setText(f"Stored: {naturalsize(size)}")
        self.stored_label.show()

    @Slot(int)
    def on_days_remaining_updated(self, days: int) -> None:
        expiry_date = datetime.strftime(
            datetime.strptime(
                datetime.isoformat(datetime.now() + timedelta(days=days)),
                "%Y-%m-%dT%H:%M:%S.%f",
            ),
            "%d %b %Y",
        )
        self.expires_label.setText(f"Expected expiry: {expiry_date}")
        self.expires_label.show()
