import logging
from base64 import b64encode
from typing import List

from PyQt5.QtCore import QPoint, QSize, Qt
from PyQt5.QtGui import QIcon, QPixmap, QStandardItem, QStandardItemModel
from PyQt5.QtWidgets import (
    QAction,
    QDialog,
    QGridLayout,
    QLabel,
    QMenu,
    QPushButton,
    QTableView,
    QWidget,
)
from twisted.internet.defer import inlineCallbacks

from gridsync import resource
from gridsync.crypto import randstr
from gridsync.gui.font import Font
from gridsync.gui.pixmap import Pixmap
from gridsync.gui.qrcode import QRCode
from gridsync.tahoe import Tahoe
from gridsync.types import TwistedDeferred


class LinkDeviceDialog(QDialog):
    def __init__(self, gateway: Tahoe) -> None:
        super().__init__()
        self.gateway = gateway
        self.device_name: str = ""

        self.setMinimumSize(QSize(600, 600))

        self.title_label = QLabel("Link Device")
        self.title_label.setAlignment(Qt.AlignCenter)
        self.title_label.setFont(Font(16))

        self.qrcode_label = QLabel("Please wait; creating link...")
        self.qrcode_label.setAlignment(Qt.AlignCenter)

        self.instructions_label = QLabel("Please wait; creating link...")
        self.instructions_label.setAlignment(Qt.AlignCenter)
        self.instructions_label.setTextInteractionFlags(
            Qt.TextSelectableByMouse
        )
        self.instructions_label.setWordWrap(True)
        self.instructions_label.hide()

        self.close_button = QPushButton("Close")
        self.close_button.setMaximumWidth(200)
        self.close_button.clicked.connect(self.close)

        layout = QGridLayout(self)
        layout.addWidget(self.title_label, 1, 1)
        layout.addWidget(self.qrcode_label, 2, 1)
        layout.addWidget(self.instructions_label, 3, 1)
        layout.addWidget(self.close_button, 4, 1, Qt.AlignCenter)

        self.gateway.devices_manager.device_linked.connect(
            self.on_device_linked
        )

    def load_qr_code(self, device_rootcap: str) -> None:
        token = self.gateway.bridge.add_pending_link(
            self.device_name, device_rootcap
        )
        pb = b64encode(self.gateway.bridge.get_public_certificate()).decode()
        data = f"{self.gateway.bridge.address}/{token} {pb}"
        self.qrcode_label.setPixmap(QPixmap(QRCode(data).scaled(400, 400)))
        self.instructions_label.setText(
            "Scan the above QR code with the <a href='https://github.com/"
            "LeastAuthority/tahoe-lafs-android-app'>Tahoe-LAFS Android app"
            "</a> to link it with this device. Linking a device will allow "
            "it to browse and modify your folders."
        )
        self.instructions_label.show()
        logging.debug("QR code displayed with encoded data: %s", data)  # XXX

    def go(self) -> None:
        device_name = "Device-" + randstr(8)
        folders = list(self.gateway.magic_folders)
        d = self.gateway.devices_manager.add_new_device(device_name, folders)
        d.addCallback(self.load_qr_code)
        self.device_name = device_name

    def on_device_linked(self, device_name: str) -> None:
        if device_name == self.device_name:
            self.title_label.setText("Success!")
            self.qrcode_label.setPixmap(
                Pixmap(resource("green_checkmark.png"), 128)
            )
            self.instructions_label.setText(
                f"{device_name} was successfully linked!"
            )


class DevicesModel(QStandardItemModel):
    def __init__(self, gateway: Tahoe) -> None:
        super().__init__(0, 2)
        self.gateway = gateway

        self.setHeaderData(0, Qt.Horizontal, "Device Name")
        self.setHeaderData(1, Qt.Horizontal, "Linked Folders")

        self.gateway.devices_manager.device_linked.connect(
            self.on_device_linked
        )
        self.populate()

    def add_device(self, name: str, folders: List[str]) -> None:
        items = self.findItems(name, Qt.MatchExactly, 0)
        if items:
            return  # Item already in model
        name_item = QStandardItem(QIcon(resource("cellphone.png")), name)
        folders_item = QStandardItem(", ".join(sorted(folders)))
        self.appendRow([name_item, folders_item])

    def remove_device(self, name: str) -> None:
        items = self.findItems(name, Qt.MatchExactly, 0)
        if items:
            self.removeRow(items[0].row())

    @inlineCallbacks
    def populate(self) -> TwistedDeferred[None]:
        sharemap = yield self.gateway.devices_manager.get_sharemap()
        for device_name, folders in sharemap.items():
            self.add_device(device_name, folders)

    def on_device_linked(self, device_name: str) -> None:
        self.populate()
        logging.debug("Successfully linked %s", device_name)


class DevicesTableView(QTableView):
    def __init__(self, gateway: Tahoe) -> None:
        super().__init__()
        self.gateway = gateway

        self._model = DevicesModel(gateway)

        self.setModel(self._model)

        self.setColumnWidth(0, 200)
        self.setShowGrid(False)
        self.setContextMenuPolicy(Qt.CustomContextMenu)
        self.setSelectionBehavior(QTableView.SelectRows)
        self.setSelectionMode(QTableView.ExtendedSelection)

        vertical_header = self.verticalHeader()
        vertical_header.hide()

        horizontal_header = self.horizontalHeader()
        horizontal_header.setHighlightSections(False)
        horizontal_header.setDefaultAlignment(Qt.AlignLeft | Qt.AlignVCenter)
        horizontal_header.setStretchLastSection(True)

        self.customContextMenuRequested.connect(self.on_right_click)

    def _selected_devices(self) -> List[str]:
        devices = []
        selected = self.selectedIndexes()
        if selected:
            for index in selected:
                item = self._model.itemFromIndex(index)
                if item.column() == 0:
                    devices.append(item.text())
        return devices

    @inlineCallbacks
    def _remove_selected(self, _: bool) -> TwistedDeferred[None]:
        selected = self._selected_devices()
        for device in selected:
            self._model.remove_device(device)
        yield self.gateway.devices_manager.remove_devices(selected)

    def on_right_click(self, position: QPoint) -> None:
        menu = QMenu(self)
        selected = self._selected_devices()
        if len(selected) >= 2:
            text = "Unlink devices..."
        else:
            text = "Unlink device..."
        remove_action = QAction(QIcon(resource("cellphone-erase.png")), text)
        remove_action.triggered.connect(self._remove_selected)
        menu.addAction(remove_action)
        menu.exec_(self.viewport().mapToGlobal(position))


class DevicesView(QWidget):
    def __init__(self, gateway: Tahoe) -> None:
        super().__init__()
        self.gateway = gateway

        self.link_device_dialogs: List = []

        self.table_view = DevicesTableView(gateway)

        self.link_device_button = QPushButton(" Link Device...")
        self.link_device_button.setIcon(QIcon(resource("qrcode-white.png")))
        self.link_device_button.setStyleSheet(
            "background: green; color: white"
        )
        self.link_device_button.setFixedSize(150, 32)
        self.link_device_button.clicked.connect(
            self.on_link_device_button_clicked
        )

        layout = QGridLayout(self)
        layout.addWidget(self.link_device_button)
        layout.addWidget(self.table_view)

    def on_link_device_button_clicked(self) -> None:
        dialog = LinkDeviceDialog(self.gateway)
        self.link_device_dialogs.append(dialog)
        dialog.show()
        dialog.go()
        # TODO: Remove on close
