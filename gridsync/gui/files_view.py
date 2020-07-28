# -*- coding: utf-8 -*-

from PyQt5.QtCore import QPoint, QSize, QSortFilterProxyModel, Qt
from PyQt5.QtCore import pyqtSignal as Signal
from PyQt5.QtGui import QMovie
from PyQt5.QtWidgets import (
    QAbstractItemView,
    QHeaderView,
    QStyledItemDelegate,
    QTableView,
)

from gridsync import resource
from gridsync.gui.font import Font
from gridsync.gui.files_model import FilesModel
from gridsync.monitor import MagicFolderChecker


class StatusItemDelegate(QStyledItemDelegate):
    def __init__(self, view):
        super().__init__(view)
        self.view = view
        self.waiting_movie = QMovie(resource("waiting.gif"))
        self.waiting_movie.setCacheMode(True)
        self.waiting_movie.frameChanged.connect(self.on_frame_changed)
        self.sync_movie = QMovie(resource("sync.gif"))
        self.sync_movie.setCacheMode(True)
        self.sync_movie.frameChanged.connect(self.on_frame_changed)

    def on_frame_changed(self):
        values = self.view.source_model.status_dict.values()
        if (
            MagicFolderChecker.LOADING in values
            or MagicFolderChecker.SYNCING in values
            or MagicFolderChecker.SCANNING in values
        ):
            self.view.viewport().update()
        else:
            self.waiting_movie.setPaused(True)
            self.sync_movie.setPaused(True)

    def paint(self, painter, option, index):
        pixmap = None
        status = index.data(Qt.UserRole)
        if status == MagicFolderChecker.LOADING:
            self.waiting_movie.setPaused(False)
            pixmap = self.waiting_movie.currentPixmap().scaled(
                32, 32, Qt.KeepAspectRatio, Qt.SmoothTransformation
            )
        elif status in (
            MagicFolderChecker.SYNCING,
            MagicFolderChecker.SCANNING,
        ):
            self.sync_movie.setPaused(False)
            pixmap = self.sync_movie.currentPixmap().scaled(
                32, 32, Qt.KeepAspectRatio, Qt.SmoothTransformation
            )
        if pixmap:
            point = option.rect.topLeft()
            painter.drawPixmap(QPoint(point.x(), point.y() + 5), pixmap)
            option.rect = option.rect.translated(pixmap.width(), 0)
        super().paint(painter, option, index)


class FilesView(QTableView):

    location_updated = Signal(str)

    def __init__(self, gui, gateway):  # pylint: disable=too-many-statements
        super().__init__()
        self.gui = gui
        self.gateway = gateway

        self.location: str = ""

        self.source_model = FilesModel(self)

        self.proxy_model = QSortFilterProxyModel()
        self.proxy_model.setSourceModel(self.source_model)
        self.proxy_model.setFilterKeyColumn(self.source_model.NAME_COLUMN)
        self.proxy_model.setFilterRole(Qt.UserRole)

        self.setModel(self.proxy_model)
        self.setItemDelegateForColumn(
            self.source_model.STATUS_COLUMN, StatusItemDelegate(self)
        )
        self.setFont(Font(12))

        self.setAcceptDrops(True)
        self.setAlternatingRowColors(True)
        self.setColumnWidth(0, 100)
        self.setColumnWidth(1, 150)
        self.setColumnWidth(2, 115)
        self.setColumnWidth(3, 90)
        self.setColumnWidth(4, 10)
        self.setContextMenuPolicy(Qt.CustomContextMenu)
        # self.setHeaderHidden(True)
        # self.setRootIsDecorated(False)
        self.setSortingEnabled(True)
        self.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.setSelectionBehavior(QTableView.SelectRows)
        self.setSelectionMode(QAbstractItemView.ExtendedSelection)
        self.setFocusPolicy(Qt.NoFocus)
        # font = QFont()
        # font.setPointSize(12)
        self.setShowGrid(False)
        self.setIconSize(QSize(32, 32))
        self.setWordWrap(False)

        vertical_header = self.verticalHeader()
        vertical_header.setSectionResizeMode(QHeaderView.Fixed)
        vertical_header.setDefaultSectionSize(42)
        vertical_header.hide()

        horizontal_header = self.horizontalHeader()
        horizontal_header.setHighlightSections(False)
        horizontal_header.setDefaultAlignment(Qt.AlignLeft | Qt.AlignVCenter)
        horizontal_header.setFont(Font(11))
        horizontal_header.setFixedHeight(30)
        horizontal_header.setStretchLastSection(False)
        horizontal_header.setSectionResizeMode(0, QHeaderView.Stretch)
        horizontal_header.setSectionResizeMode(1, QHeaderView.Stretch)
        horizontal_header.setSectionResizeMode(2, QHeaderView.Stretch)
        # horizontal_header.setSectionResizeMode(3, QHeaderView.Stretch)
        # horizontal_header.setSectionResizeMode(4, QHeaderView.Stretch)
        # self.header().setSectionResizeMode(2, QHeaderView.Stretch)
        # self.header().setSectionResizeMode(3, QHeaderView.Stretch)
        # self.setIconSize(QSize(24, 24))

        self.doubleClicked.connect(self.on_double_click)
        # self.customContextMenuRequested.connect(self.on_right_click)

        self.update_location(self.gateway.name)  # start in "root" directory

        self.source_model.populate()

    def update_location(self, location: str) -> None:
        self.proxy_model.setFilterRegularExpression(f"^{location}$")
        self.location = location
        self.location_updated.emit(location)
        print("location updated:", location)

    def on_double_click(self, index):
        source_index = self.proxy_model.mapToSource(index)
        source_item = self.source_model.itemFromIndex(source_index)
        row = source_item.row()
        name_item = self.source_model.item(row, self.source_model.NAME_COLUMN)
        # TODO: Update location if location is a directory, open otherwise
        location = name_item.data(Qt.UserRole)
        text = name_item.text()
        self.update_location(f"{location}/{text}")
