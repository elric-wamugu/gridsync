# -*- coding: utf-8 -*-
from __future__ import annotations

import logging
import webbrowser
from datetime import datetime, timedelta
from typing import TYPE_CHECKING

from humanize import naturalsize
from PyQt5.QtCore import Qt
from PyQt5.QtCore import pyqtSlot as Slot
from PyQt5.QtGui import QIcon, QPainter
from PyQt5.QtWidgets import (
    QGridLayout,
    QGroupBox,
    QLabel,
    QPushButton,
    QSizePolicy,
    QSpacerItem,
    QWidget,
)
from twisted.internet.defer import inlineCallbacks

from gridsync import APP_NAME, resource
from gridsync.desktop import get_browser_name
from gridsync.gui.charts import ZKAPBarChartView
from gridsync.gui.font import Font
from gridsync.gui.voucher import VoucherCodeDialog
from gridsync.types import TwistedDeferred
from gridsync.voucher import generate_voucher

if TYPE_CHECKING:
    from gridsync.gui import Gui  # pylint: disable=cyclic-import
    from gridsync.tahoe import Tahoe  # pylint: disable=cyclic-import


class UsageView(QWidget):
    def __init__(self, gateway: Tahoe, gui: Gui) -> None:
        super().__init__()
        self.gateway = gateway
        self.gui = gui

        self._zkaps_used: int = 0
        self._zkaps_cost: int = 0
        self._zkaps_remaining: int = 0
        self._zkaps_total: int = 0
        self._zkaps_period: int = 0
        self._last_purchase_date: str = "Not available"
        self._expiry_date: str = "Not available"
        self._amount_stored: str = "Not available"

        self.is_commercial_grid = bool(
            "zkap_payment_url_root" in gateway.settings
        )

        self.groupbox = QGroupBox()

        self.title = QLabel("Storage-time")
        font = Font(11)
        font.setBold(True)
        self.title.setFont(font)
        self.title.setAlignment(Qt.AlignCenter)
        self.title.hide()

        self.explainer_label = QLabel(
            f"The {APP_NAME} app will gradually consume your storage-time to "
            "keep your data saved."
        )
        font = Font(10)
        font.setItalic(True)
        self.explainer_label.setFont(font)
        self.explainer_label.setAlignment(Qt.AlignCenter)
        self.explainer_label.hide()

        if self.is_commercial_grid:
            action = "buy storage-time"
        else:
            action = "add storage-time using a voucher code"
        self.zkaps_required_label = QLabel(
            "You currently have 0 GB-months available.\n\nIn order to store "
            f"data with {gateway.name}, you will need to {action}."
        )
        self.zkaps_required_label.setAlignment(Qt.AlignCenter)
        self.zkaps_required_label.setWordWrap(True)

        self.chart_view = ZKAPBarChartView(self.gateway)
        self.chart_view.setFixedHeight(128)
        self.chart_view.setRenderHint(QPainter.Antialiasing)
        self.chart_view.hide()

        self.info_label = QLabel()
        self.info_label.setFont(Font(10))

        if self.is_commercial_grid:
            browser = get_browser_name()
            self.button = QPushButton(f"Buy storage-time in {browser} ")
            self.button.setIcon(QIcon(resource("globe-white.png")))
            self.button.setLayoutDirection(Qt.RightToLeft)
        else:
            self.button = QPushButton("Use voucher code")
        self.button.setStyleSheet("background: green; color: white")
        self.button.setFixedSize(240, 32)
        self.button.clicked.connect(self.on_button_clicked)

        self.voucher_link = QLabel("<a href>I have a voucher code</a>")
        self.voucher_link.linkActivated.connect(self.on_voucher_link_clicked)
        if not self.is_commercial_grid:
            self.voucher_link.hide()

        layout = QGridLayout()
        layout.addItem(QSpacerItem(0, 0, 0, QSizePolicy.Expanding), 10, 0)
        layout.addWidget(self.title, 20, 0)
        layout.addWidget(self.explainer_label, 30, 0)
        layout.addWidget(self.zkaps_required_label, 40, 0)
        layout.addItem(QSpacerItem(0, 0, 0, QSizePolicy.Expanding), 50, 0)
        layout.addWidget(self.chart_view, 60, 0)
        layout.addWidget(self.info_label, 70, 0, Qt.AlignCenter)
        layout.addItem(QSpacerItem(0, 0, 0, QSizePolicy.Expanding), 80, 0)
        layout.addWidget(self.button, 90, 0, 1, 1, Qt.AlignCenter)
        layout.addWidget(self.voucher_link, 100, 0, 1, 1, Qt.AlignCenter)
        layout.addItem(QSpacerItem(0, 0, 0, QSizePolicy.Expanding), 110, 0)

        self.groupbox.setLayout(layout)

        main_layout = QGridLayout(self)
        main_layout.addWidget(self.groupbox)

        self.gateway.monitor.zkaps_redeemed.connect(self.on_zkaps_redeemed)
        self.gateway.monitor.zkaps_updated.connect(self.on_zkaps_updated)
        # self.gateway.monitor.zkaps_renewal_cost_updated.connect(
        #    self.on_zkaps_renewal_cost_updated
        # )
        self.gateway.monitor.zkaps_price_updated.connect(
            self.on_zkaps_renewal_cost_updated
        )
        self.gateway.monitor.days_remaining_updated.connect(
            self.on_days_remaining_updated
        )
        self.gateway.monitor.total_folders_size_updated.connect(
            self.on_total_folders_size_updated
        )
        self.gateway.monitor.low_zkaps_warning.connect(
            self.on_low_zkaps_warning
        )

    @Slot()
    def on_voucher_link_clicked(self) -> None:
        voucher, ok = VoucherCodeDialog.get_voucher()
        if ok:
            self.gateway.zkapauthorizer.add_voucher(voucher)

    @inlineCallbacks
    def _open_zkap_payment_url(self) -> TwistedDeferred[None]:
        voucher = generate_voucher()  # TODO: Cache to disk
        payment_url = self.gateway.zkapauthorizer.zkap_payment_url(voucher)
        logging.debug("Opening payment URL %s ...", payment_url)
        if webbrowser.open(payment_url):
            logging.debug("Browser successfully launched")
        else:  # XXX/TODO: Raise a user-facing error
            logging.error("Error launching browser")
        yield self.gateway.zkapauthorizer.add_voucher(voucher)

    @Slot()
    def on_button_clicked(self) -> None:
        if self.is_commercial_grid:
            self._open_zkap_payment_url()
        else:
            self.on_voucher_link_clicked()

    def _update_info_label(self) -> None:
        zkapauthorizer = self.gateway.zkapauthorizer
        self.info_label.setText(
            f"Last purchase: {self._last_purchase_date} ("
            f"{self.chart_view.chart._convert(zkapauthorizer.zkap_batch_size)} "
            f"{zkapauthorizer.zkap_unit_name}s)     "
            f"Expected expiry: {self._expiry_date}"
        )

    @Slot(str)
    def on_zkaps_redeemed(self, timestamp: str) -> None:
        self._last_purchase_date = datetime.strftime(
            datetime.strptime(timestamp, "%Y-%m-%dT%H:%M:%S.%f"), "%d %b %Y"
        )
        self.zkaps_required_label.hide()
        self.explainer_label.show()
        self.chart_view.show()
        self._update_info_label()

    def _update_chart(self) -> None:
        if self._zkaps_remaining:
            self.zkaps_required_label.hide()
            self.title.show()
            self.explainer_label.show()
            self.chart_view.show()
        self.chart_view.chart.update(
            self._zkaps_used,
            self._zkaps_cost,
            self._zkaps_remaining,
            self._zkaps_period,
        )
        self.gui.main_window.toolbar.update_actions()  # XXX

    @Slot(int, int)
    def on_zkaps_updated(self, used: int, remaining: int) -> None:
        self._zkaps_used = used
        self._zkaps_remaining = remaining
        self._zkaps_total = used + remaining
        self._update_chart()

    @Slot(int, int)
    def on_zkaps_renewal_cost_updated(self, cost: int, period: int) -> None:
        self._zkaps_cost = cost
        self._zkaps_period = period
        self._update_chart()

    @Slot(int)
    def on_days_remaining_updated(self, days: int) -> None:
        self._expiry_date = datetime.strftime(
            datetime.strptime(
                datetime.isoformat(datetime.now() + timedelta(days=days)),
                "%Y-%m-%dT%H:%M:%S.%f",
            ),
            "%d %b %Y",
        )
        self._update_info_label()

    @Slot(object)
    def on_total_folders_size_updated(self, size: int) -> None:
        self._amount_stored = naturalsize(size)
        self._update_info_label()

    def on_low_zkaps_warning(self) -> None:
        action = "buy" if self.is_commercial_grid else "add"
        self.gui.show_message(
            "Low storage-time",
            f"Your storage-time is running low. Please {action} more "
            "storage-time to prevent data-loss.",
        )
        self.gui.main_window.show_usage_view()  # XXX
